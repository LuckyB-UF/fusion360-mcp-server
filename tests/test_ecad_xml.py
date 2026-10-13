"""Tests for the EAGLE XML design builder (addon/server/ecad_xml.py)."""

from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent / "addon" / "server"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_load("ecad_core")
ex = _load("ecad_xml")

_LBR = (Path(__file__).parent / "fixtures" / "classic.lbr").read_text()
LIBS = ex.libraries_from_xml(_LBR, "C:/libs/classic.lbr")

SPEC = {
    "parts": [
        {"name": "R1", "library": "classic", "device": "R-EU_R0603",
         "value": "10k", "attributes": {"MPN": "RC0603FR-0710KL"}},
        {"name": "R2", "library": "classic", "deviceset": "R-EU_",
         "device": "R0603", "value": "4k7", "board": [10, 5], "board_angle": 90},
        {"name": "GND1", "library": "classic", "device": "GND"},
        {"name": "IC1", "library": "classic", "device": "LM358D",
         "value": "LM358", "side": "bottom"},
    ],
    "nets": [
        {"name": "MID", "pins": ["R1.2", "R2.1", "IC1.A.+IN"]},
        {"name": "GND", "pins": ["R2.2", "GND1.GND", "IC1.V-"]},
    ],
    "outline": {"width": 30, "height": 20},
    "classes": [{"number": 1, "name": "power", "width": 0.5,
                 "clearance": 0.3, "drill": 0.4}],
}


def _build(spec=SPEC):
    out = ex.build(spec, LIBS)
    return out, ET.fromstring(out["sch"].split("\n", 2)[2]), \
        ET.fromstring(out["brd"].split("\n", 2)[2])


def test_library_named_after_file():
    assert list(LIBS) == ["classic"]
    assert not ex.is_managed(LIBS["classic"])


def test_list_devices_search():
    hits = ex.list_devices(LIBS, "op amp")
    assert [h["full_name"] for h in hits] == ["LM358D"]
    assert hits[0]["gates"] == ["A", "B", "P"]
    assert "+IN" in hits[0]["pins"]
    assert len(ex.list_devices(LIBS, "")) == 3


def test_schematic_parts_instances_and_nets():
    out, sch, _ = _build()
    parts = {p.get("name"): p for p in sch.iter("part")}
    assert parts["R1"].get("deviceset") == "R-EU_"
    assert parts["R1"].get("device") == "R0603"
    assert parts["R1"].find("attribute").get("value") == "RC0603FR-0710KL"
    insts = [(i.get("part"), i.get("gate")) for i in sch.iter("instance")]
    assert ("IC1", "A") in insts and ("IC1", "B") in insts and ("IC1", "P") in insts
    mid = next(n for n in sch.iter("net") if n.get("name") == "MID")
    refs = sorted((r.get("part"), r.get("gate"), r.get("pin"))
                  for r in mid.iter("pinref"))
    assert refs == [("IC1", "A", "+IN"), ("R1", "G$1", "2"), ("R2", "G$1", "1")]
    # every pin gets its own labelled stub segment
    assert len(mid.findall("segment")) == 3
    assert all(seg.find("label") is not None for seg in mid.findall("segment"))
    assert out["libraries"] == ["classic"]


def test_stub_leaves_pin_outward():
    _, sch, _ = _build()
    inst = next(i for i in sch.iter("instance") if i.get("part") == "R1")
    x0 = float(inst.get("x"))
    mid = next(n for n in sch.iter("net") if n.get("name") == "MID")
    for seg in mid.findall("segment"):
        if seg.find("pinref").get("part") == "R1":
            w = seg.find("wire")
            # pin 2 sits at +5.08; its stub must go further right
            assert float(w.get("x1")) == pytest.approx(x0 + 5.08)
            assert float(w.get("x2")) == pytest.approx(x0 + 7.62)


def test_board_elements_signals_and_outline():
    out, _, brd = _build()
    els = {e.get("name"): e for e in brd.iter("element")}
    assert "GND1" not in els  # supply symbol has no package
    assert els["R2"].get("rot") == "R90"
    assert els["IC1"].get("rot") == "MR0"
    sig = {s.get("name"): sorted((c.get("element"), c.get("pad"))
                                 for c in s.iter("contactref"))
           for s in brd.iter("signal")}
    assert sig["MID"] == [("IC1", "3"), ("R1", "2"), ("R2", "1")]
    assert sig["GND"] == [("IC1", "4"), ("R2", "2")]
    outline = [w for w in brd.find("drawing/board/plain") if w.get("layer") == "20"]
    assert len(outline) == 4
    cls = {c.get("number"): c for c in brd.iter("class")}
    assert cls["1"].find("clearance").get("value") == "0.3"
    assert {p["name"] for p in out["placed"]} == {"R1", "R2", "IC1"}


def test_auto_placement_stays_inside_outline():
    out, _, _ = _build()
    for p in out["placed"]:
        assert 0 < p["x"] < 30 and 0 < p["y"] < 20, p


def test_rounded_outline_has_arcs():
    spec = dict(SPEC, outline={"width": 30, "height": 20, "corner_radius": 2})
    _, _, brd = _build(spec)
    wires = list(brd.find("drawing/board/plain"))
    assert len(wires) == 8
    assert sum(1 for w in wires if w.get("curve")) == 4


@pytest.mark.parametrize("change, match", [
    ({"nets": [{"name": "X", "pins": ["IC1.OUT"]}]}, "ambiguous"),
    ({"nets": [{"name": "X", "pins": ["R1.9"]}]}, "no pin 9"),
    ({"nets": [{"name": "X", "pins": ["R9.1"]}]}, "no part R9"),
    ({"nets": [{"name": "A", "pins": ["R1.1"]},
               {"name": "B", "pins": ["R1.1"]}]}, "both A and B"),
    ({"parts": [{"name": "R1", "library": "nope", "device": "X"}]}, "not loaded"),
    ({"parts": [{"name": "R1", "library": "classic", "device": "R-EU_R9999"}]},
     "not found"),
    ({"outline": None}, "outline is required"),
])
def test_spec_errors(change, match):
    with pytest.raises(ex.SpecError, match=match):
        ex.build(dict(SPEC, **change), LIBS)


def test_managed_library_refused():
    managed = _LBR.replace("<library>", '<library urn="urn:adsk.eagle:library:1">')
    libs = ex.libraries_from_xml(managed, "m.lbr")
    spec = {"parts": [{"name": "R1", "library": "m", "device": "R-EU_R0603"}],
            "outline": {"width": 10, "height": 10}}
    with pytest.raises(ex.SpecError, match="managed"):
        ex.build(spec, libs)


def test_libraries_from_schematic_file():
    _, sch_root, _ = _build()
    text = ET.tostring(sch_root, encoding="unicode")
    libs = ex.libraries_from_xml(text, "x.sch")
    assert "classic" in libs

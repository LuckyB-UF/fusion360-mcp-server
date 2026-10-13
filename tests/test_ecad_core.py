"""Tests for the pure electronics core (addon/server/ecad_core.py).

The module has no Fusion imports, so it is loaded straight from the add-in
folder by path.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "addon" / "server" / "ecad_core.py"
_spec = importlib.util.spec_from_file_location("ecad_core", _PATH)
ec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ec)


# ── command builders ────────────────────────────────────────────────


def test_fmt_trims_and_rounds():
    assert ec.fmt(1.0) == "1"
    assert ec.fmt(2.54) == "2.54"
    assert ec.fmt(0.123456) == "0.1235"
    assert ec.fmt(-0.00001) == "0"
    with pytest.raises(ValueError):
        ec.fmt(float("nan"))


def test_quote_doubles_single_quotes_and_rejects_newlines():
    assert ec.quote("R1") == "'R1'"
    assert ec.quote("it's") == "'it''s'"
    with pytest.raises(ValueError):
        ec.quote("a\nb")


def test_token_quotes_only_when_needed():
    assert ec.token("R-EU_R0603") == "R-EU_R0603"
    assert ec.token("my lib") == "'my lib'"


def test_layer_number_names_and_inner():
    assert ec.layer_number("top") == 1
    assert ec.layer_number("Bottom") == 16
    assert ec.layer_number("inner2") == 2
    assert ec.layer_number("20") == 20
    with pytest.raises(ValueError):
        ec.layer_number("inner16")
    with pytest.raises(ValueError):
        ec.layer_number("nonsense")


def test_cmd_add_full():
    line = ec.cmd_add("R-EU_R0603", "rcl", "R1", 10, 20.5, angle=90)
    assert line == "ADD R-EU_R0603@rcl 'R1' R90 (10 20.5)"


def test_cmd_add_mirrored_with_gate():
    line = ec.cmd_add("LM358", "linear", "U1", 0, 0, 180, True, gate="A")
    assert line == "ADD LM358@linear 'U1' A MR180 (0 0)"


def test_cmd_net_and_wire_and_via():
    assert ec.cmd_net("GND", [(0, 0), (2.54, 0)]) == "NET 'GND' (0 0) (2.54 0)"
    assert ec.cmd_wire([(0, 0), (5, 0)], 0.4, "VIN") == "WIRE 'VIN' 0.4 (0 0) (5 0)"
    assert ec.cmd_via("GND", 1, 2, 0.6) == "VIA 'GND' 0.6 round (1 2)"
    with pytest.raises(ValueError):
        ec.cmd_net("X", [(0, 0)])
    with pytest.raises(ValueError):
        ec.cmd_via("GND", 0, 0, shape="hex")


def test_cmd_polygon_closes_ring():
    line = ec.cmd_polygon("GND", [(0, 0), (10, 0), (10, 10)], 0.3)
    assert line == "POLYGON 'GND' 0.3 (0 0) (10 0) (10 10) (0 0)"


def test_rotate_abs_and_orientation():
    assert ec.cmd_rotate_abs("U1", 90) == "ROTATE =R90 'U1'"
    assert ec.cmd_rotate_abs("U1", -90, mirror=True) == "ROTATE =MR270 'U1'"
    assert ec.orientation(450) == "R90"


def test_script_adds_grid_and_semicolons():
    s = ec.script(["MOVE 'R1' (1 2)", "", "RATSNEST;"])
    assert s == "GRID MM;\nMOVE 'R1' (1 2);\nRATSNEST;\n"
    with pytest.raises(ValueError):
        ec.script(["MOVE\nX"])


def test_outline_rectangle_and_rounded():
    lines = ec.outline_lines(width_mm=50, height_mm=30)
    assert lines[0] == "LAYER 20"
    assert lines[1] == "WIRE 0 (0 0) (50 0) (50 30) (0 30) (0 0)"
    rounded = ec.outline_lines(width_mm=50, height_mm=30, corner_radius=3)
    assert len(rounded) == 1 + 4 + 4
    assert any("+90" in ln for ln in rounded)
    with pytest.raises(ValueError):
        ec.outline_lines(width_mm=10, height_mm=10, corner_radius=6)
    with pytest.raises(ValueError):
        ec.outline_lines()


def test_pour_and_text_setup():
    assert ec.pour_setup_lines(isolate=0.3, rank=2, thermals=True) == [
        "CHANGE POUR SOLID",
        "CHANGE ISOLATE 0.3",
        "CHANGE RANK 2",
        "CHANGE THERMALS ON",
    ]
    with pytest.raises(ValueError):
        ec.pour_setup_lines(rank=9)
    assert ec.text_setup_lines(1.2, 12)[2] == "CHANGE FONT VECTOR"


# ── geometry ─────────────────────────────────────────────────────────


def test_transform_point_rotation_and_mirror():
    x, y = ec.transform_point(1, 0, 10, 10, 90)
    assert (round(x, 6), round(y, 6)) == (10, 11)
    x, y = ec.transform_point(1, 0, 0, 0, 0, mirror=True)
    assert (x, y) == (-1, 0)


def test_stub_end_points_away_from_symbol():
    assert ec.stub_end(5.08, 0, 0, 0) == (7.62, 0)
    assert ec.stub_end(-5.08, 0, 0, 0) == (-7.62, 0)
    assert ec.stub_end(0, -5.08, 0, 0) == (0, -7.62)


def test_point_in_polygon():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert ec.point_in_polygon(5, 5, sq)
    assert not ec.point_in_polygon(15, 5, sq)


def test_stitching_points_respect_edges_and_obstacles():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    pts = ec.stitching_points(sq, pitch=2, edge_clearance=1, stagger=False)
    assert pts and all(1 <= x <= 9 and 1 <= y <= 9 for x, y in pts)
    blocked = ec.stitching_points(sq, 2, 1, obstacles=[(5, 5, 2.5)], stagger=False)
    assert all(math.hypot(x - 5, y - 5) >= 2.5 for x, y in blocked)
    assert len(blocked) < len(pts)


def test_bbox_overlap():
    assert ec.bbox_overlap((0, 0, 2, 2), (1, 1, 3, 3))
    assert not ec.bbox_overlap((0, 0, 1, 1), (2, 2, 3, 3))


# ── calculators ──────────────────────────────────────────────────────


def test_trace_width_matches_ipc2221_reference():
    r = ec.trace_width(1.0, 10, 1.0)
    assert abs(r["width_mil"] - 11.8) < 0.2
    assert abs(r["width_mm"] - 0.30) < 0.01
    internal = ec.trace_width(1.0, 10, 1.0, layer="internal")
    assert internal["width_mm"] > r["width_mm"] * 2


def test_trace_width_reports_drop():
    r = ec.trace_width(13, 20, 2.0, length_mm=50)
    assert r["voltage_drop_mv"] > 0
    assert r["power_loss_mw"] > 0


def test_parse_si():
    assert ec.parse_si("4k7") == pytest.approx(4700)
    assert ec.parse_si("10k") == pytest.approx(10_000)
    assert ec.parse_si("100n") == pytest.approx(1e-7)
    assert ec.parse_si("2R2") == pytest.approx(2.2)
    assert ec.parse_si("0.1uF") == pytest.approx(1e-7)
    assert ec.parse_si(47) == 47.0
    with pytest.raises(ValueError):
        ec.parse_si("abc")


def test_si_format():
    assert ec.si(4700, "Ω") == "4.7kΩ"
    assert ec.si(1e-7, "F") == "100nF"


def test_e_series():
    e96 = ec.e_series_values("E96", 1, 10)
    assert 1.02 in e96 and 4.99 in e96 and 9.76 in e96
    assert len(ec.E_SERIES["E96"]) == 96
    assert ec.nearest_e(4800, "E24")["nearest"] == pytest.approx(4700)
    with pytest.raises(ValueError):
        ec.e_series_values("E7", 1, 10)


def test_divider_finds_accurate_pair():
    r = ec.divider(24.0, 3.0, "E24", 10e3, 200e3)
    best = r["best"][0]
    assert abs(best["error_pct"]) < 1.0
    assert 10e3 <= best["r_top"] + best["r_bottom"] <= 200e3


def test_divider_with_fixed_top():
    r = ec.divider(5.0, 3.3, "E96", top=10e3)
    assert r["best"][0]["r_top"] == 10e3


def test_microstrip_roundtrip():
    z = ec.microstrip_impedance(0.3, 0.2, 4.4, 0.035)["z0_ohm"]
    assert z == pytest.approx(53.05, abs=0.1)
    w = ec.microstrip_width_for(z, 0.2, 4.4, 0.035)["width_mm"]
    assert w == pytest.approx(0.3, abs=0.001)


def test_led_rc_power_via():
    led = ec.led_resistor(5, 2, 10)
    assert led["r_pick"] >= 300 and led["current_ma"] <= 10
    assert ec.rc_filter(r_ohm=10e3, c_f=100e-9)["fc_hz"] == pytest.approx(159.15, 0.01)
    assert ec.resistor_power(100, v=5)["power_w"] == pytest.approx(0.25)
    assert ec.via_current(0.3)["current_a"] > 0.5
    with pytest.raises(ValueError):
        ec.rc_filter(r_ohm=1)


def test_calculate_dispatch():
    assert ec.calculate("parse_value", value="4k7")["value"] == pytest.approx(4700)
    with pytest.raises(ValueError):
        ec.calculate("nope")


# ── reports ──────────────────────────────────────────────────────────

PARTS = [
    {"name": "R10", "value": "10k", "device": "R-EU_R0603", "package": "R0603",
     "attributes": {"MPN": "RC0603FR-0710KL"}},
    {"name": "R2", "value": "10k", "device": "R-EU_R0603", "package": "R0603",
     "attributes": {"MPN": "RC0603FR-0710KL"}},
    {"name": "C1", "value": "100n", "device": "C-EU_C0603", "package": "C0603",
     "attributes": {}},
    {"name": "GND1", "value": "GND", "device": "GND", "package": None},
    {"name": "R3", "value": "1k", "device": "R-EU_R0603", "package": "R0603",
     "populate": False},
]


def test_bom_groups_and_skips():
    b = ec.bom(PARTS)
    assert b["line_items"] == 2
    first = b["rows"][0]
    assert first["refs"] == "C1"
    r_row = [r for r in b["rows"] if r["value"] == "10k"][0]
    assert r_row["qty"] == 2 and r_row["refs"] == "R2, R10"
    assert "GND1" in b["skipped_no_package_or_dnp"]
    assert "R3" in b["skipped_no_package_or_dnp"]
    assert b["missing_mpn"] == ["C1"]
    assert b["csv"].splitlines()[0].startswith("qty,refs,value")


def test_pick_and_place():
    pnp = ec.pick_and_place([
        {"name": "U1", "value": "ESP32", "package": "MOD", "x": 10, "y": 5,
         "angle": 90, "mirror": False},
        {"name": "C1", "value": "100n", "package": "C0603", "x": 1, "y": 2,
         "angle": 0, "mirror": True},
        {"name": "J1", "x": 0, "y": 0, "smd": False},
    ])
    assert pnp["count"] == 2 and pnp["bottom"] == 1
    assert pnp["rows"][0]["Designator"] == "C1"
    assert pnp["rows"][1]["Mid X"] == "10.0000mm"


def test_netlist_text_sorted():
    t = ec.netlist_text([
        {"name": "VIN",
         "pins": [{"part": "U1", "pin": "1"}, {"part": "C1", "pin": "1"}]},
        {"name": "GND", "pins": [{"part": "C1", "pin": "2"}]},
    ])
    assert t == "GND: C1.2\nVIN: C1.1 U1.1\n"


def test_summarize_errors():
    s = ec.summarize_errors([
        {"description": "Clearance", "x": 1, "y": 2, "state": "Active"},
        {"description": "Clearance", "x": 3, "y": 4, "state": "Approved"},
        {"description": "Overlap", "x": 5, "y": 6},
    ])
    assert s["total"] == 3 and s["active"] == 2
    assert s["groups"][0]["description"] == "Clearance"


# ── review ───────────────────────────────────────────────────────────


def test_power_and_ground_names():
    assert ec.is_power_net("+3V3")
    assert ec.is_power_net("VBUS")
    assert ec.is_power_net("24V")
    assert ec.is_ground_net("GND") and ec.is_ground_net("AGND")
    assert not ec.is_power_net("SDA")


def test_review_finds_real_problems():
    parts = [
        {"name": "R1", "value": "", "device": "R", "package": "R0603"},
        {"name": "U1", "value": "ESP32", "device": "ESP32", "package": "MOD",
         "attributes": {"MPN": "ESP32-S3-WROOM-1"}},
        {"name": "C1", "value": "100n", "device": "C", "package": "C0603"},
    ]
    nets = [
        {"name": "+3V3", "pins": [{"part": "U1", "pin": "2"},
                                  {"part": "C1", "pin": "1"}]},
        {"name": "N$4", "pins": [{"part": "R1", "pin": "1"}]},
    ]
    elements = [
        {"name": "U1", "x": 10, "y": 10, "bbox": (5, 5, 15, 15)},
        {"name": "C1", "x": 40, "y": 10, "bbox": (39, 9, 41, 11)},
        {"name": "R1", "x": 12, "y": 12, "bbox": (11, 11, 13, 13)},
    ]
    signals = [
        {"name": "+3V3", "unrouted": 1, "track_widths": [0.2]},
        {"name": "GND", "unrouted": 0, "track_widths": []},
    ]
    r = ec.review(parts, nets, elements, signals,
                  outline=[(0, 0), (30, 0), (30, 30), (0, 30)],
                  power_currents={"+3V3": 2.0})
    checks = {f["check"] for f in r["findings"]}
    assert {"missing_value", "single_pin_net", "outside_outline",
            "courtyard_overlap", "unrouted", "track_too_narrow",
            "no_ground_pour", "decoupling_distance"} <= checks
    assert not r["passed"]
    assert r["findings"][0]["severity"] == "error"


def test_review_clean_design_passes():
    parts = [{"name": "R1", "value": "10k", "device": "R", "package": "R0603",
              "attributes": {"MPN": "X"}}]
    nets = [{"name": "A", "pins": [{"part": "R1", "pin": "1"},
                                   {"part": "R1", "pin": "2"}]}]
    r = ec.review(parts, nets)
    assert r["passed"]


def test_interactive_risk_blocks_dialog_commands():
    risky = ["USE", "ADD R-EU_R0603 (0 0)", "ADD", "DRC", "AUTO", "MENU",
             "EXPORT;", "OPEN", "ADD R-EU_R0603@rcl 'R1' R0 (0 0)", "COPY C4"]
    for line in risky:
        assert ec.interactive_risk(line), line
    safe = ["DRC ;", "AUTO ;", "ERC",
            "USE rcl", "NET 'GND' (0 0) (2.54 0)", "GRID MM", ""]
    for line in safe:
        assert ec.interactive_risk(line) is None, line


def test_check_script_raises_on_first_risky_line():
    with pytest.raises(ValueError, match="ecad_build_design"):
        ec.check_script(["GRID MM", "ADD R-EU_R0603 (0 0)"])
    ec.check_script(["GRID MM", "WIRE 0.25 (0 0) (1 1)"])

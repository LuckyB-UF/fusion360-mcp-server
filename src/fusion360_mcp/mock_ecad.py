"""Mock responses for the electronics (ecad_*) tools, for ``--mode mock``."""

from __future__ import annotations

from typing import Any

_PARTS = [
    {"name": "C1", "value": "100n", "device": "C-EU_C0603", "package": "C0603",
     "library": "rcl", "attributes": {"MPN": "CL10B104KB8NNNC"},
     "gates": [{"gate": "G$1", "sheet": 1, "x": 20.32, "y": 10.16, "angle": 90}]},
    {"name": "R1", "value": "10k", "device": "R-EU_R0603", "package": "R0603",
     "library": "rcl", "attributes": {},
     "gates": [{"gate": "G$1", "sheet": 1, "x": 10.16, "y": 10.16, "angle": 0}]},
]

_NETS = [
    {"name": "GND", "pins": [{"part": "C1", "pin": "2"}]},
    {"name": "VIN", "pins": [{"part": "R1", "pin": "1"}, {"part": "C1", "pin": "1"}]},
]

_ELEMENTS = [
    {"name": "C1", "value": "100n", "package": "C0603", "x": 12.0, "y": 8.0,
     "angle": 90.0, "mirror": False, "locked": False,
     "bbox": [11.2, 7.2, 12.8, 8.8]},
    {"name": "R1", "value": "10k", "package": "R0603", "x": 8.0, "y": 8.0,
     "angle": 0.0, "mirror": False, "locked": False,
     "bbox": [7.2, 7.6, 8.8, 8.4]},
]

_CHANGES = {"parts": 0, "nets": 0, "elements": 0, "signals": 0, "wires": 0,
            "vias": 0, "polygons": 0}


def _changes(**kw) -> dict:
    return {**_CHANGES, **kw}


def _ok(**kw) -> dict:
    return kw


def _new_design(_p: dict) -> dict:
    return _ok(created=True, design="Untitled Electronics", editor="schematic")


def _open_editor(p: dict) -> dict:
    return _ok(editor=p.get("editor", "schematic"), sheet=p.get("sheet", 1))


def _save_design(p: dict) -> dict:
    return _ok(saved=True, milestone=bool(p.get("milestone")))


def _get_design(_p: dict) -> dict:
    return _ok(
        design="Mock Board",
        editor="board",
        sheets=1,
        parts=len(_PARTS),
        nets=len(_NETS),
        elements=len(_ELEMENTS),
        signals=2,
        unrouted=1,
        board_size_mm=[30.0, 20.0],
        copper_layers=[1, 16],
        classes=[{"number": 0, "name": "default", "width": 0.0,
                  "clearance": 0.0, "drill": 0.0}],
        libraries=["rcl", "supply1"],
        erc_checked=False,
        drc_checked=False,
    )


def _list_parts(p: dict) -> dict:
    return _ok(count=len(_PARTS), parts=_PARTS)


def _list_nets(p: dict) -> dict:
    out = _ok(count=len(_NETS), nets=_NETS)
    if p.get("netlist_text"):
        out["netlist_text"] = "GND: C1.2\nVIN: C1.1 R1.1\n"
    return out


def _list_elements(_p: dict) -> dict:
    return _ok(count=len(_ELEMENTS), elements=_ELEMENTS)


def _list_signals(_p: dict) -> dict:
    return _ok(count=2, signals=[
        {"name": "GND", "class": 0, "connections": 1, "unrouted": 0,
         "track_widths": [], "length_mm": {}, "vias": 0, "has_pour": True},
        {"name": "VIN", "class": 0, "connections": 2, "unrouted": 1,
         "track_widths": [0.4], "length_mm": {"1": 4.0}, "vias": 0,
         "has_pour": False},
    ])


def _search_library(p: dict) -> dict:
    return _ok(query=p.get("query"), count=1, libraries=["rcl", "supply1"],
               truncated=False, results=[
                   {"library": "rcl", "deviceset": "R-EU_", "device": "R0603",
                    "full_name": "R-EU_R0603", "package": "R0603",
                    "gates": ["G$1"], "pins": ["1", "2"], "technologies": [""],
                    "description": "RESISTOR, European symbol",
                    "managed": False}])


def _render(p: dict) -> dict:
    # 1x1 transparent PNG
    return _ok(editor=p.get("editor", "board"), dpi=p.get("dpi", 300),
               image_format="png",
               image_base64=("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
                             "nGNgYGD4DwABBAEAwS2OUAAAAABJRU5ErkJggg=="))


def _run_erc(_p: dict) -> dict:
    return _ok(total=1, active=1, groups=[
        {"description": "Only one pin on net GND", "count": 1,
         "examples": [{"x": 20.32, "y": 7.62, "sheet": 1}]}])


def _run_drc(_p: dict) -> dict:
    return _ok(total=0, active=0, groups=[])


def _review(_p: dict) -> dict:
    return _ok(passed=False, counts={"error": 1, "warning": 1, "info": 1},
               findings=[
                   {"severity": "error", "check": "unrouted",
                    "message": "Signal VIN has 1 unrouted connection(s)",
                    "refs": []},
                   {"severity": "warning", "check": "single_pin_net",
                    "message": "Net GND connects only C1.2", "refs": ["C1"]},
                   {"severity": "info", "check": "missing_mpn",
                    "message": "R1 has no MPN attribute", "refs": ["R1"]},
               ])


def _edit(**changes):
    def handler(p: dict) -> dict:
        return _ok(script_lines=3, changes=_changes(**changes))
    return handler


def _add_part(p: dict) -> dict:
    return _ok(added=p.get("name") or "C2", copied_from=p.get("like") or "C1",
               device="C-EU_C0603", changes=_changes(parts=1, elements=1))


def _build_design(p: dict) -> dict:
    parts = p.get("parts") or []
    return _ok(ok=True, design=p.get("name") or "mcp_design", seconds=14.2,
               parts=len(parts), elements=len(parts),
               nets=len(p.get("nets") or []), libraries=["rcl"],
               placed=[{"name": x.get("name"), "x": 5.0, "y": 5.0, "angle": 0,
                        "side": "top"} for x in parts],
               files={"sch": "C:/Temp/mcp_design.sch",
                      "brd": "C:/Temp/mcp_design.brd"})


def _connect(p: dict) -> dict:
    return _ok(net=p.get("net"), connected=p.get("pins", []),
               changes=_changes(nets=1))


def _command(p: dict) -> dict:
    cmds = p.get("commands")
    n = len(cmds) if isinstance(cmds, list) else len(str(cmds).splitlines())
    return _ok(lines=n, changes=_changes())


def _export_bom(p: dict) -> dict:
    return _ok(path=p.get("path"), line_items=2, placements=2,
               csv="qty,refs,value,package,device,MPN,MANUFACTURER\n"
                   "1,C1,100n,C0603,C-EU_C0603,CL10B104KB8NNNC,\n"
                   "1,R1,10k,R0603,R-EU_R0603,,\n",
               missing_mpn=["R1"])


def _export_pnp(p: dict) -> dict:
    return _ok(path=p.get("path"), count=2, top=2, bottom=0,
               csv="Designator,Val,Package,Mid X,Mid Y,Rotation,Layer\n"
                   "C1,100n,C0603,12.0000mm,8.0000mm,90,Top\n"
                   "R1,10k,R0603,8.0000mm,8.0000mm,0,Top\n")


def _export_netlist(p: dict) -> dict:
    return _ok(path=p.get("path"), nets=2,
               netlist_text="GND: C1.2\nVIN: C1.1 R1.1\n")


def _export_gerbers(p: dict) -> dict:
    out = p.get("output_dir", "C:/out")
    return _ok(output_dir=out, files=["copper_top.gbr", "copper_bottom.gbr",
                                      "drill_1_16.xln"],
               zip=f"{out}/gerbers.zip" if p.get("zip", True) else None)


def _export_odb(p: dict) -> dict:
    return _ok(output_dir=p.get("output_dir"), files=["odb.tgz"])


def _export_eagle(p: dict) -> dict:
    return _ok(kind=p.get("kind"), path=p.get("path"), bytes=12345)


def _calculate(p: dict) -> dict:
    if p.get("kind") == "trace_width":
        return _ok(kind="trace_width", width_mm=0.3, width_mil=11.8,
                   standard="IPC-2221")
    return _ok(kind=p.get("kind"), params=p.get("params", {}))


ECAD_MOCKS: dict[str, Any] = {
    "ecad_new_design": _new_design,
    "ecad_open_editor": _open_editor,
    "ecad_save_design": _save_design,
    "ecad_get_design": _get_design,
    "ecad_list_parts": _list_parts,
    "ecad_list_nets": _list_nets,
    "ecad_list_elements": _list_elements,
    "ecad_list_signals": _list_signals,
    "ecad_search_library": _search_library,
    "ecad_render": _render,
    "ecad_run_erc": _run_erc,
    "ecad_run_drc": _run_drc,
    "ecad_review": _review,
    "ecad_add_sheet": lambda p: _ok(sheet=2, description=p.get("description")),
    "ecad_add_part": _add_part,
    "ecad_build_design": _build_design,
    "ecad_set_part": lambda p: _ok(name=p.get("name"), changes=_changes()),
    "ecad_connect": _connect,
    "ecad_set_outline": _edit(wires=4),
    "ecad_place": lambda p: _ok(placed=[i["name"] for i in p.get("items", [])],
                                changes=_changes()),
    "ecad_route": _edit(wires=1),
    "ecad_add_vias": _edit(vias=4),
    "ecad_add_pour": _edit(polygons=1),
    "ecad_add_holes": _edit(),
    "ecad_add_text": _edit(),
    "ecad_set_net_class": _edit(),
    "ecad_autoroute": _edit(wires=6),
    "ecad_ripup": _edit(wires=-6),
    "ecad_ratsnest": _edit(),
    "ecad_command": _command,
    "ecad_run_ulp": lambda p: _ok(ulp=p.get("ulp"), changes=_changes()),
    "ecad_export_bom": _export_bom,
    "ecad_export_pick_place": _export_pnp,
    "ecad_export_netlist": _export_netlist,
    "ecad_export_gerbers": _export_gerbers,
    "ecad_export_odb": _export_odb,
    "ecad_export_eagle": _export_eagle,
    "ecad_calculate": _calculate,
}

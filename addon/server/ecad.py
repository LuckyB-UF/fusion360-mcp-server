"""
Fusion Electronics handlers (schematic + PCB).

How it works:
    * Reads go through ``adsk.electron`` (Fusion's Electronics API, which
      is read-only) and come back as plain dicts in millimetres.
    * Writes are EAGLE command scripts built by ``ecad_core`` and run with
      Fusion's ``Electron.runScript`` text command.  Every write reads the
      design again afterwards and reports what changed, so a command that
      silently did nothing shows up as zero changes.

All methods run on Fusion's main thread (dispatched by EventBridge).
"""

from __future__ import annotations

import base64
import glob
import math
import os
import re
import shutil
import tempfile
import time

import adsk.core

from . import ecad_core as core
from . import get_logger

try:  # Electronics API ships with Fusion since May 2026
    import adsk.electron as electron
except Exception:  # pragma: no cover - older Fusion
    electron = None

log = get_logger("ecad")

# EAGLE internal resolution: 1/320000 inch.
_U2MM = 25.4 / 320000.0


class EcadError(RuntimeError):
    """Raised for electronics-specific failures (classified by hints)."""


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------


def _items(coll):
    """Iterate a Fusion collection or an EcadObjectVector."""
    if coll is None:
        return []
    try:
        n = coll.count
    except Exception:
        n = None
    if n is not None and hasattr(coll, "item"):
        return [coll.item(i) for i in range(n)]
    try:
        return list(coll)
    except Exception:
        return []


def _g(obj, *names, default=None):
    """First readable attribute of *obj* among *names*."""
    for n in names:
        try:
            v = getattr(obj, n)
        except Exception:
            continue
        if v is not None:
            return v
    return default


def _safe(fn, default=None):
    """Call *fn*; Fusion raises (not returns None) for missing links."""
    try:
        return fn()
    except Exception:
        return default


def _pump(cond, timeout: float = 20.0, step: float = 0.1) -> bool:
    """Let Fusion process events until cond() is true or timeout."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        adsk.doEvents()
        if _safe(cond, False):
            return True
        time.sleep(step)
    return bool(_safe(cond, False))


def _name(obj, default=""):
    return _g(obj, "name", default=default) if obj is not None else default


def _mm(u) -> float:
    try:
        return round(float(u) * _U2MM, 4)
    except Exception:
        return 0.0


def _angle(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _attrs(obj) -> dict:
    out = {}
    for a in _items(_g(obj, "attributes")):
        n = _g(a, "name")
        if n:
            out[str(n)] = str(_g(a, "value", default=""))
    return out


def _bundle_dirs() -> list[str]:
    """Folders holding Fusion's bundled EAGLE examples (ulp, cam, dru)."""
    roots = []
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Autodesk",
                        "webdeploy", "production")
    for d in sorted(glob.glob(os.path.join(base, "*")), key=os.path.getmtime,
                    reverse=True):
        p = os.path.join(d, "Applications", "Electron", "LibEagle", "examples")
        if os.path.isdir(p):
            roots.append(p)
    return roots


def _find_bundled(filename: str, kind: str) -> str | None:
    for root in _bundle_dirs():
        for p in glob.glob(os.path.join(root, "**", filename), recursive=True):
            return p
        if kind:
            for p in glob.glob(os.path.join(root, "**", "*" + kind), recursive=True):
                if os.path.basename(p).lower() == filename.lower():
                    return p
    return None


# ----------------------------------------------------------------------
# handler
# ----------------------------------------------------------------------


class EcadHandler:
    def __init__(self, app):
        self.app = app

    def commands(self) -> dict:
        return {
            "ecad_new_design": self.new_design,
            "ecad_open_editor": self.open_editor,
            "ecad_save_design": self.save_design,
            "ecad_get_design": self.get_design,
            "ecad_list_parts": self.list_parts,
            "ecad_list_nets": self.list_nets,
            "ecad_list_elements": self.list_elements,
            "ecad_list_signals": self.list_signals,
            "ecad_search_library": self.search_library,
            "ecad_render": self.render,
            "ecad_run_erc": self.run_erc,
            "ecad_run_drc": self.run_drc,
            "ecad_review": self.review,
            "ecad_add_sheet": self.add_sheet,
            "ecad_add_part": self.add_part,
            "ecad_set_part": self.set_part,
            "ecad_connect": self.connect,
            "ecad_set_outline": self.set_outline,
            "ecad_place": self.place,
            "ecad_route": self.route,
            "ecad_add_vias": self.add_vias,
            "ecad_add_pour": self.add_pour,
            "ecad_add_holes": self.add_holes,
            "ecad_add_text": self.add_text,
            "ecad_set_net_class": self.set_net_class,
            "ecad_autoroute": self.autoroute,
            "ecad_ripup": self.ripup,
            "ecad_ratsnest": self.ratsnest,
            "ecad_command": self.command,
            "ecad_run_ulp": self.run_ulp,
            "ecad_export_bom": self.export_bom,
            "ecad_export_pick_place": self.export_pick_place,
            "ecad_export_netlist": self.export_netlist,
            "ecad_export_gerbers": self.export_gerbers,
            "ecad_export_odb": self.export_odb,
            "ecad_export_eagle": self.export_eagle,
            "ecad_calculate": self.calculate,
        }

    # ------------------------------------------------------------------
    # context
    # ------------------------------------------------------------------

    def _require_api(self):
        if electron is None:
            raise EcadError(
                "This Fusion has no Electronics API (adsk.electron). "
                "Update Fusion to May 2026 or later."
            )

    def _design(self):
        """The active EcadDesign (schematic + board container)."""
        self._require_api()
        docs = [self.app.activeDocument] + _items(self.app.documents)
        for doc in docs:
            if doc is None:
                continue
            d = electron.EcadDesignDocument.cast(doc)
            if d:
                return d.ecadDesign
            s = electron.SchematicDocument.cast(doc)
            design = _safe(lambda: s.schematic.parentDesign) if s else None
            if design is not None:
                return design
            b = electron.BoardDocument.cast(doc)
            design = _safe(lambda: b.board.parentDesign) if b else None
            if design is not None:
                return design
        raise EcadError(
            "No electronics design is open. Open one, or call ecad_new_design."
        )

    def _sch(self):
        s = _safe(lambda: self._design().schematic)
        if s is None:
            raise EcadError(
                "This electronics design has no schematic yet. Call "
                "ecad_open_editor schematic to create it."
            )
        return s

    def _brd(self):
        b = _safe(lambda: self._design().board)
        if b is None:
            raise EcadError(
                "This electronics design has no PCB yet. Call "
                "ecad_open_editor board to create it."
            )
        return b

    def _sch_or_none(self):
        return _safe(lambda: self._design().schematic)

    def _brd_or_none(self):
        return _safe(lambda: self._design().board)

    def _active_editor(self) -> str | None:
        doc = self.app.activeDocument
        if doc is None or electron is None:
            return None
        if electron.BoardDocument.cast(doc):
            return "board"
        if electron.SchematicDocument.cast(doc):
            return "schematic"
        return None

    # Fusion command ids that create the schematic / PCB of a design.
    _CREATE_CMDS = {
        "schematic": ("NewElectronSchDocumentCommand",),
        "board": ("NewElectronBrdDocumentCommand", "NewElectronPcbDocumentCommand",
                  "NewElectronBoardDocumentCommand"),
    }

    def _activate(self, editor: str):
        if self._active_editor() == editor:
            return
        target = (self._brd_or_none() if editor == "board"
                  else self._sch_or_none())
        if target is not None:
            doc = _safe(lambda: target.parentDocument)
            if doc is not None and _safe(doc.activate, False):
                if _pump(lambda: self._active_editor() == editor, 10):
                    return
        else:
            # The editor does not exist yet: create it inside this design.
            self._design()
            ui = self.app.userInterface
            for cid in self._CREATE_CMDS[editor]:
                cmd = ui.commandDefinitions.itemById(cid)
                if cmd:
                    cmd.execute()
                    if _pump(lambda: self._active_editor() == editor, 30):
                        return
        raise EcadError(f"Could not open the {editor} editor")

    # ------------------------------------------------------------------
    # running EAGLE commands
    # ------------------------------------------------------------------

    def _exec_text(self, cmd: str) -> str:
        t0 = time.monotonic()
        try:
            r = self.app.executeTextCommand(cmd)
        except Exception as exc:
            raise EcadError(f"Fusion refused '{cmd[:120]}': {exc}") from exc
        log.debug("%s -> %r (%.2fs)", cmd[:80], r, time.monotonic() - t0)
        return r or ""

    def _run(self, lines: list[str], editor: str | None = None,
             grid_mm: bool = True) -> dict:
        """Run command lines as one .scr script; return read-back changes."""
        if editor:
            self._activate(editor)
        before = self._snapshot()
        text = core.script(lines, grid_mm=grid_mm)
        fd, path = tempfile.mkstemp(prefix="mcp_ecad_", suffix=".scr")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            out = self._exec_text(f'Electron.runScript "{path}"')
            adsk.doEvents()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        after = self._snapshot()
        changes = {k: after.get(k, 0) - before.get(k, 0) for k in after}
        return {"script_lines": len(text.splitlines()), "fusion_output": out,
                "changes": changes}

    def _snapshot(self) -> dict:
        snap = {"parts": 0, "nets": 0, "elements": 0, "signals": 0,
                "wires": 0, "vias": 0, "polygons": 0}
        try:
            self._design()
        except Exception:
            return snap
        sch, brd = self._sch_or_none(), self._brd_or_none()
        if sch is not None:
            snap["parts"] = len(_items(sch.parts))
            snap["nets"] = len(_items(sch.nets))
        if brd is not None:
            snap["elements"] = len(_items(brd.elements))
            sigs = _items(brd.signals)
            snap["signals"] = len(sigs)
            for s in sigs:
                snap["wires"] += len(_items(s.wires))
                snap["vias"] += len(_items(s.vias))
                snap["polygons"] += len(_items(s.polyPours))
        return snap

    # ------------------------------------------------------------------
    # readers (adsk objects -> plain dicts, mm)
    # ------------------------------------------------------------------

    def _read_parts(self, include_pins=False) -> list[dict]:
        out = []
        for p in _items(self._sch().parts):
            dev = _g(p, "device")
            pkg = _g(dev, "package") if dev is not None else None
            lib = _g(dev, "library") if dev is not None else None
            gates = []
            for inst in _items(_g(p, "instances")):
                gates.append({
                    "gate": _name(_g(inst, "gate")),
                    "sheet": _g(inst, "sheet", "sheetNumber"),
                    "x": _mm(_g(inst, "x", default=0)),
                    "y": _mm(_g(inst, "y", default=0)),
                    "angle": _angle(_g(inst, "angle", default=0)),
                    "mirror": bool(_g(inst, "mirror", default=False)),
                })
            d = {
                "name": _name(p),
                "value": _g(p, "value", default="") or "",
                "device": _name(dev),
                "deviceset": _name(_g(p, "deviceset")),
                "package": _name(pkg) or None,
                "library": _name(lib) if lib is not None and not isinstance(
                    lib, str) else (lib or ""),
                "attributes": _attrs(p),
                "gates": gates,
            }
            if include_pins:
                d["pins"] = self._part_pins(p)
            out.append(d)
        return out

    def _part_pins(self, part) -> list[dict]:
        pins = []
        for inst in _items(_g(part, "instances")):
            gate = _g(inst, "gate")
            sym = _g(gate, "symbol") if gate is not None else None
            ix, iy = _mm(_g(inst, "x", default=0)), _mm(_g(inst, "y", default=0))
            ang = _angle(_g(inst, "angle", default=0))
            mir = bool(_g(inst, "mirror", default=False))
            for pin in _items(_g(sym, "pins")):
                px, py = core.transform_point(
                    _mm(_g(pin, "x", default=0)), _mm(_g(pin, "y", default=0)),
                    ix, iy, ang, mir)
                pins.append({
                    "pin": _name(pin),
                    "gate": _name(gate),
                    "sheet": _g(inst, "sheet", "sheetNumber"),
                    "x": round(px, 4), "y": round(py, 4),
                    "inst_x": ix, "inst_y": iy,
                    "net": _name(_g(pin, "net")) or None,
                })
        return pins

    def _read_nets(self) -> list[dict]:
        out = []
        for n in _items(self._sch().nets):
            pins = []
            seen = set()
            refs = []
            for seg in _items(_g(n, "segments")):
                refs.extend(_items(_g(seg, "pinRefs", "pinrefs")))
            refs.extend(_items(_g(n, "pinRefs", "pinrefs")))
            for r in refs:
                part = _name(_g(r, "part"))
                pin = _name(_g(r, "pin"))
                if (part, pin) in seen:
                    continue
                seen.add((part, pin))
                pins.append({"part": part, "pin": pin,
                             "gate": _name(_g(r, "instance", "gate"))})
            cls = _g(n, "netClass", "class_")
            out.append({"name": _name(n), "class": _name(cls) or None,
                        "pins": pins})
        return out

    def _read_elements(self) -> list[dict]:
        out = []
        for e in _items(self._brd().elements):
            x, y = _mm(_g(e, "x", default=0)), _mm(_g(e, "y", default=0))
            ang = _angle(_g(e, "angle", default=0))
            mir = bool(_g(e, "mirror", default=False))
            pkg = _g(e, "package")
            bbox = None
            area = _g(pkg, "area") if pkg is not None else None
            if area is not None:
                try:
                    corners = [
                        core.transform_point(_mm(cx), _mm(cy), x, y, ang, mir)
                        for cx, cy in ((area.x1, area.y1), (area.x2, area.y1),
                                       (area.x2, area.y2), (area.x1, area.y2))
                    ]
                    xs = [c[0] for c in corners]
                    ys = [c[1] for c in corners]
                    bbox = [round(min(xs), 4), round(min(ys), 4),
                            round(max(xs), 4), round(max(ys), 4)]
                except Exception:
                    bbox = None
            smd = None
            if pkg is not None:
                n_smd = len(_items(_g(pkg, "smds")))
                n_pad = len(_items(_g(pkg, "pads")))
                smd = n_smd > 0 and n_pad == 0
            out.append({
                "name": _name(e),
                "value": _g(e, "value", default="") or "",
                "package": _name(pkg) or None,
                "x": x, "y": y, "angle": ang, "mirror": mir,
                "side": "bottom" if mir else "top",
                "locked": bool(_g(e, "locked", default=False)),
                "populate": bool(_g(e, "populate", default=True)),
                "smd": smd,
                "bbox": bbox,
                "attributes": _attrs(e),
            })
        return out

    def _read_signals(self) -> list[dict]:
        out = []
        for s in _items(self._brd().signals):
            widths, length, unrouted = set(), {}, 0
            for w in _items(s.wires):
                layer = _g(w, "layer")
                ln = layer if isinstance(layer, int) else _g(layer, "number")
                if ln == 19:
                    unrouted += 1
                    continue
                width = _mm(_g(w, "width", default=0))
                widths.add(width)
                seg = math.hypot(
                    _mm(_g(w, "x2", default=0)) - _mm(_g(w, "x1", default=0)),
                    _mm(_g(w, "y2", default=0)) - _mm(_g(w, "y1", default=0)))
                length[str(ln)] = round(length.get(str(ln), 0) + seg, 3)
            cls = _g(s, "netClass")
            out.append({
                "name": _name(s),
                "class": _name(cls) if cls is not None and not isinstance(
                    cls, (int, str)) else cls,
                "connections": len(_items(_g(s, "contactRefs"))),
                "unrouted": unrouted,
                "track_widths": sorted(widths),
                "length_mm": length,
                "vias": len(_items(s.vias)),
                "has_pour": len(_items(s.polyPours)) > 0,
            })
        return out

    def _read_errors(self, product) -> list[dict]:
        out = []
        for e in _items(_g(product, "errors")):
            state = _g(e, "state")
            out.append({
                "code": _g(e, "code"),
                "description": _g(e, "description"),
                "layer": _g(e, "layer"),
                "x": _mm(_g(e, "x", default=0)),
                "y": _mm(_g(e, "y", default=0)),
                "sheet": _g(e, "sheet"),
                "state": str(state) if state is not None else None,
                "signature": _g(e, "signature"),
            })
        return out

    def _outline(self) -> list[tuple[float, float]] | None:
        """Board outline as a polygon (chained layer-20 wires)."""
        segs = []
        for w in _items(self._brd().wires):
            layer = _g(w, "layer")
            ln = layer if isinstance(layer, int) else _g(layer, "number")
            if ln != 20:
                continue
            segs.append(((_mm(w.x1), _mm(w.y1)), (_mm(w.x2), _mm(w.y2))))
        if not segs:
            return None
        ring = [segs[0][0], segs[0][1]]
        rest = segs[1:]
        while rest:
            tail = ring[-1]
            for i, (a, b) in enumerate(rest):
                if math.dist(a, tail) < 0.01:
                    ring.append(b)
                    rest.pop(i)
                    break
                if math.dist(b, tail) < 0.01:
                    ring.append(a)
                    rest.pop(i)
                    break
            else:
                break
        if len(ring) < 3:
            xs = [p for s in segs for p in (s[0][0], s[1][0])]
            ys = [p for s in segs for p in (s[0][1], s[1][1])]
            return [(min(xs), min(ys)), (max(xs), min(ys)),
                    (max(xs), max(ys)), (min(xs), max(ys))]
        return ring

    # ------------------------------------------------------------------
    # design / session tools
    # ------------------------------------------------------------------

    def new_design(self, with_board: bool = False):
        ui = self.app.userInterface
        cmd = ui.commandDefinitions.itemById("NewElectronDesignDocumentCommand")
        if not cmd:
            raise EcadError(
                "Could not find Fusion's 'new electronics design' command. "
                "Create one from File > New Electronics Design, then retry."
            )
        before = self.app.activeDocument
        cmd.execute()
        if not _pump(lambda: self.app.activeDocument != before and
                     electron.EcadDesignDocument.cast(self.app.activeDocument), 20):
            raise EcadError("Fusion did not open a new electronics design")
        self._activate("schematic")
        if with_board:
            self._activate("board")
        return {"created": True, "design": _name(self._design()),
                "editor": self._active_editor()}

    def open_editor(self, editor: str, sheet: int | None = None):
        self._activate(editor)
        if editor == "schematic" and sheet:
            self._run([core.cmd_edit_sheet(sheet)], grid_mm=False)
        return {"editor": self._active_editor(), "sheet": sheet}

    def save_design(self, description: str = "", milestone: bool = False):
        doc = self._design().parentDocument
        if doc is None:
            raise EcadError("Cannot find the design's document")
        ok = doc.saveMilestone(description) if milestone else doc.save(description)
        return {"saved": bool(ok), "milestone": milestone, "name": doc.name}

    def get_design(self):
        design = self._design()
        sch, brd = self._sch_or_none(), self._brd_or_none()
        out = {"design": _name(design), "editor": self._active_editor(),
               "has_schematic": sch is not None, "has_board": brd is not None}
        if sch is not None:
            out["sheets"] = len(_items(sch.sheets))
            out["parts"] = len(_items(sch.parts))
            out["nets"] = len(_items(sch.nets))
            out["libraries"] = [_name(lib) for lib in _items(sch.libraries)]
            out["erc_checked"] = bool(_g(sch, "checked", default=False))
            out["erc_errors"] = len(_items(sch.errors))
        if brd is not None:
            out["elements"] = len(_items(brd.elements))
            sigs = self._read_signals()
            out["signals"] = len(sigs)
            out["unrouted"] = sum(s["unrouted"] for s in sigs)
            outline = self._outline()
            if outline:
                xs = [p[0] for p in outline]
                ys = [p[1] for p in outline]
                out["board_size_mm"] = [round(max(xs) - min(xs), 3),
                                        round(max(ys) - min(ys), 3)]
            out["copper_layers"] = [
                _g(layer, "number") for layer in _items(brd.layers)
                if _g(layer, "number") in core.COPPER_LAYERS
                and _g(layer, "used", default=False)
            ]
            out["classes"] = [
                {"number": _g(c, "number"), "name": _name(c),
                 "width": _mm(_g(c, "width", default=0)),
                 "drill": _mm(_g(c, "drill", default=0))}
                for c in _items(brd.classes) if _name(c)
            ]
            out["drc_checked"] = bool(_g(brd, "checked", default=False))
            out["drc_errors"] = len(_items(brd.errors))
        return out

    # ------------------------------------------------------------------
    # read tools
    # ------------------------------------------------------------------

    def list_parts(self, filter: str | None = None, include_pins: bool = False):
        parts = self._read_parts(include_pins)
        if filter:
            rx = re.compile(filter, re.IGNORECASE)
            parts = [p for p in parts if rx.search(p["name"]) or
                     rx.search(p["value"] or "")]
        return {"count": len(parts), "parts": parts}

    def list_nets(self, filter: str | None = None, netlist_text: bool = False):
        nets = self._read_nets()
        if filter:
            rx = re.compile(filter, re.IGNORECASE)
            nets = [n for n in nets if rx.search(n["name"])]
        out = {"count": len(nets), "nets": nets}
        if netlist_text:
            out["netlist_text"] = core.netlist_text(nets)
        return out

    def list_elements(self, filter: str | None = None):
        els = self._read_elements()
        if filter:
            rx = re.compile(filter, re.IGNORECASE)
            els = [e for e in els if rx.search(e["name"])]
        return {"count": len(els), "elements": els}

    def list_signals(self, filter: str | None = None, unrouted_only: bool = False):
        sigs = self._read_signals()
        if filter:
            rx = re.compile(filter, re.IGNORECASE)
            sigs = [s for s in sigs if rx.search(s["name"])]
        if unrouted_only:
            sigs = [s for s in sigs if s["unrouted"]]
        return {"count": len(sigs), "unrouted_total": sum(s["unrouted"] for s in sigs),
                "signals": sigs}

    def search_library(self, query: str, library: str | None = None,
                       limit: int = 40):
        rx = re.compile(query, re.IGNORECASE)
        results = []
        for lib in _items(self._sch().libraries):
            lname = _name(lib)
            if library and lname.lower() != library.lower():
                continue
            for ds in _items(_g(lib, "devicesets")):
                desc = _g(ds, "description", "headline", default="") or ""
                for dev in _items(_g(ds, "devices")):
                    pkg = _name(_g(dev, "package"))
                    hay = " ".join([_name(ds), _name(dev), pkg, desc])
                    if not rx.search(hay):
                        continue
                    results.append({
                        "library": lname,
                        "deviceset": _name(ds),
                        "device": _name(ds) + _name(dev),
                        "package": pkg,
                        "technologies": [_name(t) for t in
                                         _items(_g(dev, "technologies"))],
                        "description": re.sub(r"<[^>]+>", "", desc)[:200],
                    })
                    if len(results) >= limit:
                        return {"query": query, "count": len(results),
                                "results": results, "truncated": True}
        return {"query": query, "count": len(results), "results": results,
                "note": None if results else (
                    "Only libraries already used by this design are searched. "
                    "Add a part from the library first with ecad_command "
                    "'USE <library>' or use a known device name.")}

    def render(self, editor: str = "board", sheet: int | None = None,
               preset: str = "all", layers=None, dpi: int = 300,
               monochrome: bool = False):
        presets = {
            "all": None,
            "top": [1, 17, 18, 20, 21, 25, 27, 29, 51],
            "bottom": [16, 17, 18, 20, 22, 26, 28, 30, 52],
            "copper": list(range(1, 17)) + [17, 18, 20],
            "silk": [20, 21, 22, 25, 26],
            "outline": [20, 46],
        }
        lines = []
        if editor == "schematic" and sheet:
            lines.append(core.cmd_edit_sheet(sheet))
        show = [core.layer_number(x) for x in layers] if layers else (
            presets.get(preset) if editor == "board" else None)
        if show:
            lines.append("DISPLAY NONE " + " ".join(str(n) for n in show))
        fd, path = tempfile.mkstemp(prefix="mcp_ecad_", suffix=".png")
        os.close(fd)
        lines.append(f"EXPORT IMAGE {core.quote(path)} "
                     f"{'MONOCHROME ' if monochrome else ''}{int(dpi)}")
        if show:
            lines.append("DISPLAY LAST")
        self._run(lines, editor=editor, grid_mm=False)
        try:
            with open(path, "rb") as f:
                data = f.read()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        if not data:
            raise EcadError("EXPORT IMAGE produced no file")
        return {"editor": editor, "dpi": dpi, "bytes": len(data),
                "image_format": "png",
                "image_base64": base64.b64encode(data).decode("ascii")}

    # ------------------------------------------------------------------
    # checks
    # ------------------------------------------------------------------

    def run_erc(self):
        self._run(["ERC"], editor="schematic", grid_mm=False)
        return core.summarize_errors(self._read_errors(self._sch()))

    def run_drc(self, rules_file: str | None = None):
        lines = []
        if rules_file:
            if not os.path.isfile(rules_file):
                raise EcadError(f"Rules file not found: {rules_file}")
            lines.append(f"DRC LOAD {core.quote(rules_file)}")
        lines.append("DRC ;")
        self._run(lines, editor="board", grid_mm=False)
        return core.summarize_errors(self._read_errors(self._brd()))

    def review(self, power_currents: dict | None = None, run_checks: bool = True,
               decoupling_max_mm: float = 3.0):
        sch, board = self._sch_or_none(), self._brd_or_none()
        errors = []
        if run_checks:
            if sch is not None:
                self.run_erc()
            if board is not None:
                self.run_drc()
        if sch is not None:
            errors += self._read_errors(sch)
        if board is not None:
            errors += self._read_errors(board)
        return core.review(
            parts=self._read_parts() if sch is not None else [],
            nets=self._read_nets() if sch is not None else [],
            elements=self._read_elements() if board is not None else [],
            signals=self._read_signals() if board is not None else [],
            outline=self._outline() if board is not None else None,
            errors=errors,
            power_currents=power_currents,
            decoupling_max_mm=decoupling_max_mm,
        )

    # ------------------------------------------------------------------
    # schematic edits
    # ------------------------------------------------------------------

    def add_sheet(self, description: str | None = None):
        sch = self._sch()
        sheet = sch.sheets.create()
        n = len(_items(sch.sheets))
        lines = [core.cmd_edit_sheet(n)]
        r = self._run(lines, editor="schematic", grid_mm=False)
        if description:
            try:
                sheet.description = description
            except Exception:
                pass
        return {"sheet": n, **r}

    def add_part(self, device, library, x, y, name=None, value=None, angle=0.0,
                 mirror=False, sheet=None, gate=None, attributes=None):
        lines = []
        if sheet:
            lines.append(core.cmd_edit_sheet(sheet))
        lines.append(core.cmd_add(device, library, name, x, y, angle, mirror, gate))
        r = self._run(lines, editor="schematic")
        if r["changes"].get("parts", 0) < 1 and not gate:
            raise EcadError(
                f"ADD {device}@{library} did not add a part. Check the device "
                "name (device set + package variant) with ecad_search_library."
            )
        added = name or self._newest_part_name()
        follow = []
        if value:
            follow.append(core.cmd_value(added, value))
        for k, v in (attributes or {}).items():
            follow.append(core.cmd_attribute(added, k, v))
        if follow:
            self._run(follow, editor="schematic", grid_mm=False)
        return {"added": added, "device": device, "library": library, **r}

    def _newest_part_name(self) -> str:
        parts = _items(self._sch().parts)
        return _name(parts[-1]) if parts else ""

    def set_part(self, name, value=None, attributes=None):
        lines = []
        if value is not None:
            lines.append(core.cmd_value(name, value))
        for k, v in (attributes or {}).items():
            lines.append(core.cmd_attribute(name, k, v))
        if not lines:
            raise EcadError("Give a value or attributes to set")
        r = self._run(lines, editor="schematic", grid_mm=False)
        part = next((p for p in self._read_parts() if p["name"] == name), None)
        if part is None:
            raise EcadError(f"Part {name} not found")
        return {"name": name, "value": part["value"],
                "attributes": part["attributes"], **r}

    def connect(self, net, pins, stub_length=2.54):
        wanted = []
        for ref in pins:
            if "." not in ref:
                raise EcadError(f"Pin '{ref}' must be PART.PIN")
            part, pin = ref.split(".", 1)
            wanted.append((part, pin))
        by_part = {}
        for p in _items(self._sch().parts):
            by_part[_name(p)] = p
        lines = []
        done = []
        sheet_now = None
        for part, pin in wanted:
            p = by_part.get(part)
            if p is None:
                raise EcadError(f"Part {part} not found")
            matches = [x for x in self._part_pins(p) if x["pin"] == pin]
            if not matches:
                names = sorted({x["pin"] for x in self._part_pins(p)})
                raise EcadError(f"{part} has no pin {pin}. Pins: {', '.join(names)}")
            m = matches[0]
            if m.get("sheet") and m["sheet"] != sheet_now:
                lines.append(core.cmd_edit_sheet(m["sheet"]))
                sheet_now = m["sheet"]
            end = core.stub_end(m["x"], m["y"], m["inst_x"], m["inst_y"], stub_length)
            lines.append(core.cmd_net(net, [(m["x"], m["y"]), end]))
            done.append(f"{part}.{pin}")
        r = self._run(lines, editor="schematic")
        on_net = {f"{c['part']}.{c['pin']}" for n in self._read_nets()
                  if n["name"] == net for c in n["pins"]}
        missing = [x for x in done if x not in on_net]
        return {"net": net, "connected": sorted(on_net & set(done)),
                "not_connected": missing, **r}

    # ------------------------------------------------------------------
    # board edits
    # ------------------------------------------------------------------

    def set_outline(self, width=None, height=None, corner_radius=0.0,
                    origin=(0, 0), points=None, replace=True):
        lines = []
        if replace:
            lines += ["DISPLAY NONE 20", "GROUP ALL", "DELETE (> 0 0)",
                      "DISPLAY LAST"]
        lines += core.outline_lines(points=points, width_mm=width,
                                    height_mm=height,
                                    corner_radius=corner_radius,
                                    origin=tuple(origin))
        r = self._run(lines, editor="board")
        return {"outline": self._outline(), **r}

    def place(self, items):
        lines = []
        current = {e["name"]: e for e in self._read_elements()}
        for it in items:
            name = it["name"]
            if name not in current:
                raise EcadError(f"Element {name} is not on the board")
            if current[name]["locked"]:
                raise EcadError(f"{name} is locked; unlock it before moving")
            lines.append(core.cmd_move(name, it["x"], it["y"]))
            side = it.get("side")
            mirror = (side == "bottom") if side else current[name]["mirror"]
            angle = it.get("angle", current[name]["angle"])
            lines.append(core.cmd_rotate_abs(name, angle, mirror))
            if it.get("lock"):
                lines.append(f"LOCK {core.quote(name)}")
        r = self._run(lines, editor="board")
        after = {e["name"]: e for e in self._read_elements()}
        placed = []
        for it in items:
            e = after[it["name"]]
            placed.append({"name": e["name"], "x": e["x"], "y": e["y"],
                           "angle": e["angle"], "side": e["side"],
                           "ok": abs(e["x"] - it["x"]) < 0.01 and
                           abs(e["y"] - it["y"]) < 0.01})
        return {"placed": placed, **r}

    def route(self, signal, points, width, layer="top"):
        lines = [core.cmd_layer(layer), core.cmd_wire(points, width, signal)]
        r = self._run(lines, editor="board")
        if r["changes"].get("wires", 0) == 0:
            r["warning"] = ("No new track segments were read back. Check the "
                            "signal name and that the points are on the board.")
        return {"signal": signal, **r}

    def add_vias(self, signal, points=None, stitch_region=None,
                 stitch_outline=False, pitch=5.0, edge_clearance=1.0,
                 keepout=1.0, drill=0.3, diameter=0.6):
        pts = [tuple(p) for p in (points or [])]
        if stitch_region or stitch_outline:
            region = stitch_region or self._outline()
            if not region:
                raise EcadError("No region: give stitch_region or draw an outline")
            obstacles = []
            for e in self._read_elements():
                if e["bbox"]:
                    x1, y1, x2, y2 = e["bbox"]
                    obstacles.append(((x1 + x2) / 2, (y1 + y2) / 2,
                                      math.hypot(x2 - x1, y2 - y1) / 2 + keepout))
            for s in _items(self._brd().signals):
                for v in _items(s.vias):
                    obstacles.append((_mm(v.x), _mm(v.y), diameter + keepout))
            pts += core.stitching_points(region, pitch, edge_clearance, obstacles)
        if not pts:
            raise EcadError("No via positions: give points or a stitch region")
        lines = [f"CHANGE DRILL {core.fmt(drill)}"]
        lines += [core.cmd_via(signal, x, y, diameter) for x, y in pts]
        r = self._run(lines, editor="board")
        return {"signal": signal, "requested": len(pts), **r}

    def add_pour(self, signal, layer="top", points=None, inset=0.5, isolate=0.3,
                 rank=1, thermals=True, orphans=False, width=0.254):
        if not points:
            outline = self._outline()
            if not outline:
                raise EcadError("No outline: give points or draw the outline first")
            xs = [p[0] for p in outline]
            ys = [p[1] for p in outline]
            points = [(min(xs) + inset, min(ys) + inset),
                      (max(xs) - inset, min(ys) + inset),
                      (max(xs) - inset, max(ys) - inset),
                      (min(xs) + inset, max(ys) - inset)]
        lines = [core.cmd_layer(layer)]
        lines += core.pour_setup_lines(isolate=isolate, rank=rank,
                                       thermals=thermals, orphans=orphans)
        lines.append(core.cmd_polygon(signal, points, width))
        lines.append("RATSNEST")
        r = self._run(lines, editor="board")
        return {"signal": signal, "layer": core.layer_number(layer), **r}

    def add_holes(self, holes):
        lines = [core.cmd_hole(h["drill"], h["x"], h["y"]) for h in holes]
        r = self._run(lines, editor="board")
        return {"holes": len(holes), **r}

    def add_text(self, text, x, y, layer="tplace", size=1.0, ratio=15, angle=0.0):
        n = core.layer_number(layer)
        lines = [core.cmd_layer(n)] + core.text_setup_lines(size, ratio)
        lines.append(core.cmd_text(text, x, y, angle, mirror=n in (16, 22, 26, 28,
                                                                    52)))
        r = self._run(lines, editor="board")
        return {"text": text, "layer": n, **r}

    def set_net_class(self, number, name, width=None, clearance=None, drill=None,
                      nets=None):
        parts = [f"CLASS {int(number)} {core.quote(name)}"]
        if width is not None:
            parts.append(core.fmt(width))
            if clearance is not None:
                parts.append(core.fmt(clearance))
                if drill is not None:
                    parts.append(core.fmt(drill))
        lines = [" ".join(parts)]
        # Assign nets by picking a point on one of each net's schematic wires.
        if nets:
            pts = self._net_pick_points(nets)
            lines.append(f"CHANGE CLASS {int(number)} " +
                         " ".join(core.pt(x, y) for x, y in pts.values()))
        r = self._run(lines, editor="schematic")
        assigned = {n["name"]: n["class"] for n in self._read_nets()
                    if n["name"] in (nets or [])}
        return {"class": int(number), "name": name, "assigned": assigned, **r}

    def _net_pick_points(self, nets) -> dict:
        out = {}
        for n in _items(self._sch().nets):
            if _name(n) not in nets:
                continue
            for seg in _items(_g(n, "segments")):
                for w in _items(_g(seg, "wires")):
                    out[_name(n)] = ((_mm(w.x1) + _mm(w.x2)) / 2,
                                     (_mm(w.y1) + _mm(w.y2)) / 2)
                    break
                if _name(n) in out:
                    break
        missing = set(nets) - set(out)
        if missing:
            raise EcadError(f"Nets without schematic wires: {sorted(missing)}")
        return out

    def autoroute(self, signals=None):
        line = "AUTO " + (" ".join(core.quote(s) for s in signals) if signals
                          else "") + " ;"
        r = self._run([line], editor="board", grid_mm=False)
        left = sum(s["unrouted"] for s in self._read_signals())
        return {"unrouted_after": left, **r}

    def ripup(self, signals=None, polygons=False):
        if polygons:
            line = "RIPUP @ " + " ".join(core.quote(s) for s in (signals or []))
        elif signals:
            line = "RIPUP " + " ".join(core.quote(s) for s in signals)
        else:
            line = "RIPUP ;"
        return self._run([line], editor="board", grid_mm=False)

    def ratsnest(self):
        r = self._run(["RATSNEST"], editor="board", grid_mm=False)
        r["unrouted"] = sum(s["unrouted"] for s in self._read_signals())
        return r

    def command(self, commands, editor=None):
        lines = commands.splitlines() if isinstance(commands, str) else list(commands)
        return self._run(lines, editor=editor)

    def run_ulp(self, ulp, args=None, editor=None):
        path = ulp
        if not os.path.isfile(path):
            name = ulp if ulp.lower().endswith(".ulp") else ulp + ".ulp"
            path = _find_bundled(name, ".ulp")
            if not path:
                raise EcadError(f"ULP not found: {ulp}")
        line = f"RUN {core.quote(path)} " + " ".join(core.quote(a) for a in args or [])
        r = self._run([line], editor=editor, grid_mm=False)
        return {"ulp": path, **r}

    # ------------------------------------------------------------------
    # outputs
    # ------------------------------------------------------------------

    @staticmethod
    def _write(path, text):
        if not path:
            return None
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return os.path.abspath(path)

    def export_bom(self, path=None, group=True, attribute_columns=None):
        parts = self._read_parts()
        populate = {}
        try:
            populate = {e["name"]: e["populate"] for e in self._read_elements()}
        except Exception:
            pass
        for p in parts:
            if p["name"] in populate:
                p["populate"] = populate[p["name"]]
        b = core.bom(parts, group, attribute_columns)
        b["path"] = self._write(path, b["csv"])
        return b

    def export_pick_place(self, path=None, origin=None, style="jlcpcb",
                          include_tht=False):
        els = self._read_elements()
        if include_tht:
            for e in els:
                e["smd"] = None
        if origin is None:
            outline = self._outline()
            origin = (min(p[0] for p in outline), min(p[1] for p in outline)) \
                if outline else (0, 0)
        r = core.pick_and_place(els, tuple(origin), style)
        r["path"] = self._write(path, r["csv"])
        r["origin"] = list(origin)
        return r

    def export_netlist(self, path=None):
        nets = self._read_nets()
        text = core.netlist_text(nets)
        return {"nets": len(nets), "netlist_text": text,
                "path": self._write(path, text)}

    def _default_cam_job(self) -> str | None:
        layers = self.get_design().get("copper_layers") or [1, 16]
        n = max(2, len(layers))
        for root in _bundle_dirs():
            cands = glob.glob(os.path.join(root, "cam", "**", "*.cam"),
                              recursive=True)
            exact = [c for c in cands if f"_{n}_layer" in os.path.basename(c)]
            if exact:
                return exact[0]
        return None

    def export_gerbers(self, output_dir, cam_job=None, zip=True):
        job = cam_job or self._default_cam_job()
        if not job or not os.path.isfile(job):
            raise EcadError("No CAM job found; pass cam_job with a .cam path")
        os.makedirs(output_dir, exist_ok=True)
        before = set(os.listdir(output_dir))
        self._activate("board")
        out = self._exec_text(f'Electron.mfgexport "{output_dir}" "{job}"')
        adsk.doEvents()
        files = sorted(set(os.listdir(output_dir)) - before) or sorted(
            os.listdir(output_dir))
        if not files:
            raise EcadError(f"CAM export wrote nothing. Fusion said: {out}")
        archive = None
        if zip:
            archive = shutil.make_archive(os.path.join(output_dir, "gerbers"), "zip",
                                          output_dir)
        return {"output_dir": os.path.abspath(output_dir), "cam_job": job,
                "files": files, "zip": archive, "fusion_output": out}

    def export_odb(self, output_dir, cam_job=None):
        job = cam_job or self._default_cam_job()
        if not job:
            raise EcadError("No CAM job found; pass cam_job")
        os.makedirs(output_dir, exist_ok=True)
        self._activate("board")
        out = self._exec_text(f'Electron.mfgodb "{output_dir}" "{job}"')
        adsk.doEvents()
        return {"output_dir": os.path.abspath(output_dir), "cam_job": job,
                "files": sorted(os.listdir(output_dir)), "fusion_output": out}

    def export_eagle(self, kind, path):
        product = {"sch": self._sch_or_none(), "brd": self._brd_or_none(),
                   "lbr": self._sch_or_none()}.get(kind)
        if product is None:
            raise EcadError(f"Nothing to export for {kind}")
        mgr = product.exportManager
        make = {"sch": mgr.createEagleSchExportOptions,
                "brd": mgr.createEagleBrdExportOptions,
                "lbr": mgr.createEagleLbrExportOptions}[kind]
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        ok = mgr.execute(make(path))
        if not ok or not os.path.isfile(path):
            raise EcadError(f"Export of {kind} failed")
        return {"kind": kind, "path": os.path.abspath(path),
                "bytes": os.path.getsize(path)}

    # ------------------------------------------------------------------
    # engineering
    # ------------------------------------------------------------------

    def calculate(self, kind, params=None):
        return core.calculate(kind, **(params or {}))

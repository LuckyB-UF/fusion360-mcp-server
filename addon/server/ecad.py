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
from . import ecad_xml, get_logger

try:  # Electronics API ships with Fusion since May 2026
    import adsk.electron as electron
except Exception:  # pragma: no cover - older Fusion
    electron = None

log = get_logger("ecad")

# Internal units of adsk.electron: 320000 per mm (adsk.electron.Units.u2mm,
# confirmed live on Fusion 2705.1.30).
_U2MM = 1.0 / 320000.0


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


def _running_install() -> str | None:
    """Install folder of the Fusion that is running this add-in.

    Several versions can sit side by side under webdeploy/production, and
    the newest folder is not always the one running.
    """
    here = os.path.dirname(os.path.abspath(os.__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(here, "Applications", "Electron")):
            return here
        here = os.path.dirname(here)
    return None


def _bundle_dirs() -> list[str]:
    """Folders holding Fusion's bundled EAGLE examples (ulp, cam, dru)."""
    roots = []
    inst = _running_install()
    if inst:
        p = os.path.join(inst, "Applications", "Electron", "LibEagle", "examples")
        if os.path.isdir(p):
            roots.append(p)
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Autodesk",
                        "webdeploy", "production")
    for d in sorted(glob.glob(os.path.join(base, "*")), key=os.path.getmtime,
                    reverse=True):
        p = os.path.join(d, "Applications", "Electron", "LibEagle", "examples")
        if os.path.isdir(p) and p not in roots:
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
        # The design the tools work on.  Pinned when a tool creates or
        # imports one, because Fusion's active document can jump to another
        # open schematic between commands (seen in live testing).
        self._pinned = None

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
            "ecad_build_design": self.build_design,
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

    def _pin(self, design):
        self._pinned = design

    def _pinned_design(self):
        d = self._pinned
        if d is None:
            return None
        if not _safe(lambda: d.isValid, True) or _safe(
                lambda: d.parentDocument.isValid, True) is False:
            self._pinned = None
            return None
        return d

    def _design(self):
        """The EcadDesign the tools work on (pinned, else the active one)."""
        self._require_api()
        pinned = self._pinned_design()
        if pinned is not None:
            return pinned
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
        "board": ("NewElectronPcbDocumentCommand",),
    }

    def _editor_doc(self, editor: str):
        target = (self._brd_or_none() if editor == "board"
                  else self._sch_or_none())
        return _safe(lambda: target.parentDocument) if target is not None else None

    def _is_active(self, doc) -> bool:
        act = self.app.activeDocument
        if act is None or doc is None:
            return False
        try:
            return act == doc or (act.name == doc.name and act.isActive)
        except Exception:
            return False

    def _activate(self, editor: str):
        """Make *editor* of the working design the active document.

        Checked by document, not by editor type: with several designs open,
        "a schematic is active" is not the same as "ours is".
        """
        doc = self._editor_doc(editor)
        if doc is not None:
            if self._is_active(doc):
                return
            if _safe(doc.activate, False) and _pump(
                    lambda: self._is_active(doc), 10):
                return
            raise EcadError(f"Could not switch to the {editor} editor")
        # The editor does not exist yet: create it inside this design.
        design = self._design()
        self._pin(design)
        design_doc = _safe(lambda: design.parentDocument)
        if design_doc is not None and not self._is_active(design_doc):
            _safe(design_doc.activate)
            _pump(lambda: self._is_active(design_doc), 10)
        ui = self.app.userInterface
        for cid in self._CREATE_CMDS[editor]:
            cmd = ui.commandDefinitions.itemById(cid)
            if cmd:
                cmd.execute()
                if _pump(lambda: self._editor_doc(editor) is not None, 30):
                    new_doc = self._editor_doc(editor)
                    if self._is_active(new_doc) or (
                            _safe(new_doc.activate, False) and
                            _pump(lambda: self._is_active(new_doc), 10)):
                        return
        raise EcadError(f"Could not create the {editor} editor")

    def _stop_command(self):
        """End a command mode MOVE/ROTATE/WIRE/VIA leave running."""
        cmd = _safe(lambda: self.app.userInterface.commandDefinitions.itemById(
            "Electron::StopCommand"))
        if cmd is not None:
            _safe(cmd.execute)

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
            p = path.replace("\\", "/")
            out = self._exec_text("Electron.runScript " +
                                  (f'"{p}"' if " " in p else p))
            adsk.doEvents()
            self._stop_command()
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
        self._pin(electron.EcadDesignDocument.cast(self.app.activeDocument).ecadDesign)
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

    # Classic EAGLE libraries bundled with Fusion live inside this example
    # schematic (rcl, supply1, pinhead, diode, led, linear, ...).  Fusion's
    # own .lbr files are the managed kind the importer can't use.
    _BUNDLED_CLASSIC = ("Arduino_MEGA2560_ref.sch",)

    def _library_files(self, files=None) -> list[str]:
        out = []
        for f in files or []:
            if not os.path.isfile(f):
                raise EcadError(f"Library file not found: {f}")
            out.append(f)
        if not files:
            for name in self._BUNDLED_CLASSIC:
                p = _find_bundled(name, "")
                if p:
                    out.append(p)
        return out

    def _load_libraries(self, files=None):
        libs, layers = {}, None
        for path in self._library_files(files):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            try:
                found = ecad_xml.libraries_from_xml(text, path)
            except Exception as exc:
                raise EcadError(f"Cannot read {path}: {exc}") from exc
            for k, v in found.items():
                libs.setdefault(k, v)
            if layers is None:
                layers = ecad_xml.layers_from_xml(text)
        return libs, layers

    def search_library(self, query: str = "", library: str | None = None,
                       library_files=None, limit: int = 40):
        """Devices in classic EAGLE libraries (bundled, or files you give)."""
        libs, _ = self._load_libraries(library_files)
        if library:
            libs = {k: v for k, v in libs.items() if k.lower() == library.lower()}
        results = ecad_xml.list_devices(libs, query, limit)
        return {"query": query, "count": len(results), "results": results,
                "libraries": sorted(libs),
                "truncated": len(results) >= limit}

    def build_design(self, parts, outline, nets=None, classes=None,
                     library_files=None, name="mcp_design"):
        """Create a new design from a full spec through an EAGLE XML import."""
        libs, layers = self._load_libraries(library_files)
        spec = {"parts": parts, "nets": nets or [], "outline": outline,
                "classes": classes or []}
        try:
            built = ecad_xml.build(spec, libs, layers)
        except ecad_xml.SpecError as exc:
            raise EcadError(str(exc)) from exc
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name or "mcp_design")[:40]
        folder = tempfile.mkdtemp(prefix="mcp_ecad_build_")
        sch = os.path.join(folder, safe + ".sch").replace("\\", "/")
        brd = os.path.join(folder, safe + ".brd").replace("\\", "/")
        with open(sch, "w", encoding="utf-8") as f:
            f.write(built["sch"])
        with open(brd, "w", encoding="utf-8") as f:
            f.write(built["brd"])
        before = {d.name for d in _items(self.app.documents)}
        t0 = time.monotonic()
        out = self._exec_text(f'Electron.importSchAndBrd "{sch}" "{brd}"')

        def new_design():
            for d in _items(self.app.documents):
                if d.name in before:
                    continue
                e = electron.EcadDesignDocument.cast(d)
                if e:
                    return e.ecadDesign
            return None

        if not _pump(lambda: new_design() is not None and _safe(
                lambda: new_design().board) is not None, 60):
            raise EcadError(f"The import did not open a new design. Fusion "
                            f"said: {out!r}")
        self._pin(new_design())
        self._stop_command()
        got_parts = {p["name"] for p in self._read_parts()}
        got_elements = {e["name"] for e in self._read_elements()}
        got_nets = {n["name"]: {f"{c['part']}.{c['pin']}" for c in n["pins"]}
                    for n in self._read_nets()}
        want_parts = {p["name"] for p in built["parts"]}
        want_elements = {p["name"] for p in built["placed"]}
        missing_pins = {}
        for n in built["nets"]:
            have = got_nets.get(n["name"], set())
            gone = [p for p in n["pins"] if p.split(".")[0] + "." +
                    p.split(".")[-1] not in have]
            if gone:
                missing_pins[n["name"]] = gone
        problems = {
            "missing_parts": sorted(want_parts - got_parts),
            "missing_elements": sorted(want_elements - got_elements),
            "missing_net_pins": missing_pins,
        }
        ok = not any(problems.values())
        return {"ok": ok, "design": _name(self._design()),
                "seconds": round(time.monotonic() - t0, 1),
                "parts": len(got_parts), "elements": len(got_elements),
                "nets": len(got_nets), "libraries": built["libraries"],
                "placed": built["placed"], "files": {"sch": sch, "brd": brd},
                **({} if ok else {"problems": problems})}

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

    def add_part(self, name, like, x, y, value=None, sheet=1, gate=None,
                 attributes=None):
        """Add a part by copying one already in the design.

        EAGLE's ADD does not work from code in Fusion, so a new part is a
        copy of an existing part with the same device
        (``Electron.sch_sheet_placeinstance``).  Parts from a library the
        design does not use yet go in through ecad_build_design.
        """
        parts = {p["name"]: p for p in self._read_parts()}
        if like not in parts:
            raise EcadError(
                f"Part {like} is not in the design. Copy an existing part with "
                "the same device, or build the design with ecad_build_design.")
        if name in parts:
            raise EcadError(f"A part named {name} already exists")
        g = gate or (parts[like]["gates"][0]["gate"] if parts[like]["gates"]
                     else "G$1")
        self._activate("schematic")
        before = self._snapshot()
        out = self._exec_text(
            f"Electron.sch_sheet_placeinstance {int(sheet)} {like} {name} {g} "
            f"mm {core.fmt(x)} {core.fmt(y)}")
        adsk.doEvents()
        self._stop_command()
        after = {p["name"] for p in self._read_parts()}
        if name not in after:
            raise EcadError(f"Fusion did not add {name}. It said: {out!r}")
        follow = [core.cmd_value(name, value or parts[like]["value"])] \
            if (value or parts[like]["value"]) else []
        for k, v in (attributes or {}).items():
            follow.append(core.cmd_attribute(name, k, v))
        if follow:
            self._run(follow, editor="schematic", grid_mm=False)
        snap = self._snapshot()
        return {"added": name, "copied_from": like,
                "device": parts[like]["device"],
                "changes": {k: snap.get(k, 0) - before.get(k, 0) for k in snap},
                "note": ("Copies made this way may refuse ROTATE on the board; "
                         "rebuild with ecad_build_design if that matters.")}

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
        owner = {(c["part"], c["pin"]): n["name"] for n in self._read_nets()
                 for c in n["pins"]}
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
            current = owner.get((part, pin))
            if current == net:
                done.append(f"{part}.{pin}")
                continue
            if current:
                # NET onto another net opens a modal "merge?" question.
                raise EcadError(
                    f"{part}.{pin} is already on net {current}. Connecting it "
                    f"to {net} would merge the two nets; disconnect it first or "
                    f"rename {current} with ecad_command NAME.")
            if m.get("sheet") and m["sheet"] != sheet_now:
                lines.append(core.cmd_edit_sheet(m["sheet"]))
                sheet_now = m["sheet"]
            end = core.stub_end(m["x"], m["y"], m["inst_x"], m["inst_y"], stub_length)
            lines.append(core.cmd_net(net, [(m["x"], m["y"]), end]))
            done.append(f"{part}.{pin}")
        r = self._run(lines, editor="schematic") if lines else {
            "script_lines": 0, "changes": {}}
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
            side = it.get("side")
            if side and (side == "bottom") != current[name]["mirror"]:
                raise EcadError(
                    f"Moving {name} to the {side} side is not possible from "
                    "code: MIRROR does nothing when scripted. Set the side in "
                    "ecad_build_design instead.")
            lines.append(core.cmd_move(name, it["x"], it["y"]))
            mirror = current[name]["mirror"]
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
        try:
            core.check_script(lines)
        except ValueError as exc:
            raise EcadError(str(exc)) from exc
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

    def _check_saved(self, save_first: bool):
        doc = _safe(lambda: self._design().parentDocument)
        if doc is None:
            raise EcadError("Cannot find the design's document")
        if not _safe(lambda: doc.isSaved, True) or _safe(
                lambda: doc.isModified, False):
            if not save_first:
                raise EcadError(
                    "Fusion makes manufacturing files from the last saved "
                    "version, and this design has unsaved changes. Save it "
                    "(ecad_save_design), or pass save_first=true.")
            if not doc.save("Saved for manufacturing export"):
                raise EcadError("Saving the design failed")

    def _cam_export(self, kind, output_dir, cam_job, save_first):
        job = cam_job or self._default_cam_job()
        if not job or not os.path.isfile(job):
            raise EcadError("No CAM job found; pass cam_job with a .cam path")
        self._check_saved(save_first)
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        # Fusion ignores the folder's own name and writes to
        # <parent>/<job>/<job>.gbr/CAMOutputs/... (seen live), so collect
        # whatever it writes under <parent>/<job> and copy it in.
        stem = os.path.splitext(os.path.basename(job))[0]
        written = os.path.join(os.path.dirname(output_dir), stem)
        start = time.time() - 2
        self._activate("board")
        cmd = "Electron.mfgexport" if kind == "gerber" else "Electron.mfgodb"
        out = self._exec_text(f'{cmd} "{output_dir}" "{job}"')
        adsk.doEvents()
        files = []
        for root in {written, output_dir}:
            for dirpath, _dirs, names in os.walk(root):
                for n in names:
                    src = os.path.join(dirpath, n)
                    if os.path.getmtime(src) < start:
                        continue
                    rel = os.path.relpath(src, root)
                    dst = os.path.join(output_dir, rel)
                    if os.path.abspath(src) != os.path.abspath(dst):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                    files.append(rel.replace("\\", "/"))
        if not files:
            raise EcadError(f"CAM export wrote nothing. Fusion said: {out!r}")
        return job, sorted(set(files)), out

    def export_gerbers(self, output_dir, cam_job=None, zip=True,
                       save_first=False):
        job, files, out = self._cam_export("gerber", output_dir, cam_job,
                                           save_first)
        archive = None
        if zip:
            tmp = shutil.make_archive(
                os.path.join(tempfile.mkdtemp(prefix="mcp_cam_"), "gerbers"),
                "zip", os.path.abspath(output_dir))
            archive = os.path.join(os.path.abspath(output_dir), "gerbers.zip")
            shutil.move(tmp, archive)
        return {"output_dir": os.path.abspath(output_dir), "cam_job": job,
                "files": files, "zip": archive, "fusion_output": out}

    def export_odb(self, output_dir, cam_job=None, save_first=False):
        job, files, out = self._cam_export("odb", output_dir, cam_job,
                                           save_first)
        return {"output_dir": os.path.abspath(output_dir), "cam_job": job,
                "files": files, "fusion_output": out}

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

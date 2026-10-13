"""
Build a whole Fusion Electronics design as EAGLE XML: pure Python, no Fusion.

Why this exists: EAGLE's ADD command does not work when driven from code in
Fusion (it hits an internal assert or silently does nothing).  What does work
is writing a ``.sch`` + ``.brd`` pair and importing it with the text command
``Electron.importSchAndBrd "<sch>" "<brd>"``.  This module turns a plain
spec (libraries, parts, nets, outline, classes) into that pair.

Libraries must be classic EAGLE XML.  Fusion's managed 9.x libraries (the
ones with ``urn`` attributes and ``packages3d``) import onto the board but
leave the schematic empty, so they are refused with a clear message.

Units: every length in the spec is millimetres; EAGLE XML stores mm too.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET

try:
    from . import ecad_core as core
except ImportError:  # loaded on its own (unit tests)
    import ecad_core as core

GRID = 2.54  # schematic grid; pins and stubs land on it

# Minimal layer table for files that have no source layer table to copy.
_DEFAULT_LAYERS = [
    (1, "Top", 4), (16, "Bottom", 1), (17, "Pads", 2), (18, "Vias", 2),
    (19, "Unrouted", 6), (20, "Dimension", 15), (21, "tPlace", 7),
    (22, "bPlace", 7), (23, "tOrigins", 15), (24, "bOrigins", 15),
    (25, "tNames", 7), (26, "bNames", 7), (27, "tValues", 7),
    (28, "bValues", 7), (29, "tStop", 7), (30, "bStop", 7),
    (31, "tCream", 7), (32, "bCream", 7), (35, "tGlue", 7),
    (36, "bGlue", 7), (39, "tKeepout", 4), (40, "bKeepout", 1),
    (41, "tRestrict", 4), (42, "bRestrict", 1), (43, "vRestrict", 2),
    (44, "Drills", 7), (45, "Holes", 7), (46, "Milling", 3),
    (47, "Measures", 7), (48, "Document", 7), (49, "Reference", 7),
    (51, "tDocu", 7), (52, "bDocu", 7), (91, "Nets", 2), (92, "Busses", 1),
    (93, "Pins", 2), (94, "Symbols", 4), (95, "Names", 7), (96, "Values", 7),
    (97, "Info", 7), (98, "Guide", 6),
]


class SpecError(ValueError):
    """The design spec or a library does not fit together."""


# ======================================================================
# Libraries
# ======================================================================


def is_managed(lib: ET.Element) -> bool:
    """Fusion managed (library.io) library: breaks the schematic import."""
    if lib.get("urn"):
        return True
    if lib.find("packages3d") is not None:
        return True
    return any(el.get("urn") for el in lib.iter("deviceset"))


def libraries_from_xml(text: str, source: str = "") -> dict[str, ET.Element]:
    """Every library in an .lbr, .sch or .brd file, keyed by name.

    A .lbr holds one unnamed <library>; it takes its name from the file name.
    """
    root = ET.fromstring(text)
    drawing = root.find("drawing")
    if drawing is None:
        raise SpecError(f"{source or 'file'}: not an EAGLE XML file")
    out = {}
    single = drawing.find("library")
    if single is not None:
        name = single.get("name") or re.sub(r"\.lbr$", "", source.replace(
            "\\", "/").rsplit("/", 1)[-1], flags=re.I) or "lib"
        lib = copy.deepcopy(single)
        lib.set("name", name)
        out[name] = lib
    for lib in drawing.iter("library"):
        if lib is single:
            continue
        name = lib.get("name")
        if name and name not in out:
            out[name] = copy.deepcopy(lib)
    return out


def layers_from_xml(text: str) -> ET.Element | None:
    root = ET.fromstring(text)
    layers = root.find("drawing/layers")
    return copy.deepcopy(layers) if layers is not None else None


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return re.sub(r"<[^>]+>", " ", "".join(el.itertext())).strip()


def list_devices(libraries: dict[str, ET.Element], query: str = "",
                 limit: int = 50) -> list[dict]:
    """Search devices across libraries (regex over names and description)."""
    rx = re.compile(query or ".", re.IGNORECASE)
    out = []
    for lname, lib in libraries.items():
        for ds in lib.iterfind("devicesets/deviceset"):
            desc = _text(ds.find("description"))
            gates = [g.get("name") for g in ds.iterfind("gates/gate")]
            for dev in ds.iterfind("devices/device"):
                hay = " ".join([ds.get("name", ""), dev.get("name", ""),
                                dev.get("package") or "", desc])
                if not rx.search(hay):
                    continue
                out.append({
                    "library": lname,
                    "deviceset": ds.get("name"),
                    "device": dev.get("name", ""),
                    "full_name": ds.get("name", "") + dev.get("name", ""),
                    "package": dev.get("package"),
                    "gates": gates,
                    "pins": sorted(_device_pins(lib, ds)),
                    "technologies": [t.get("name", "") for t in
                                     dev.iterfind("technologies/technology")],
                    "description": desc[:160],
                    "managed": is_managed(lib),
                })
                if len(out) >= limit:
                    return out
    return out


def _device_pins(lib, ds) -> set[str]:
    pins = set()
    for g in ds.iterfind("gates/gate"):
        sym = lib.find(f"symbols/symbol[@name='{g.get('symbol')}']")
        if sym is not None:
            pins.update(p.get("name") for p in sym.iterfind("pin"))
    return pins


# ======================================================================
# Spec resolution
# ======================================================================


def _rot(angle: float = 0.0, mirror: bool = False) -> str:
    a = float(angle) % 360
    if a % 90:
        raise SpecError(f"Angle {angle} must be a multiple of 90")
    return ("M" if mirror else "") + f"R{int(a)}"


def _find_device(lib: ET.Element, deviceset: str | None, device: str):
    """Accept deviceset + device variant, or the full name 'R-EU_R0603'."""
    sets = list(lib.iterfind("devicesets/deviceset"))
    if deviceset:
        cands = [ds for ds in sets if ds.get("name") == deviceset]
        for ds in cands:
            for dev in ds.iterfind("devices/device"):
                if dev.get("name", "") == (device or ""):
                    return ds, dev
    else:
        for ds in sets:
            for dev in ds.iterfind("devices/device"):
                if ds.get("name", "") + dev.get("name", "") == device:
                    return ds, dev
    return None, None


class _Part:
    def __init__(self, spec: dict, lib: ET.Element, lname: str):
        self.name = spec["name"]
        self.lib, self.lname = lib, lname
        ds, dev = _find_device(lib, spec.get("deviceset"), spec.get("device", ""))
        if ds is None:
            want = (f"{spec.get('deviceset')} / {spec.get('device', '')!r}"
                    if spec.get("deviceset") else spec.get("device"))
            raise SpecError(f"{self.name}: device {want} not found in library "
                            f"{lname}. Use ecad_search_library to find it.")
        self.ds, self.dev = ds, dev
        self.value = str(spec.get("value", "") or "")
        self.attributes = {str(k): str(v) for k, v in
                           (spec.get("attributes") or {}).items()}
        techs = [t.get("name", "") for t in dev.iterfind("technologies/technology")]
        tech = spec.get("technology")
        if tech is None:
            tech = techs[0] if techs else ""
        elif techs and tech not in techs:
            raise SpecError(f"{self.name}: technology {tech!r} not in {techs}")
        self.technology = tech
        self.package = dev.get("package")
        self.gates = [(g.get("name"), g.get("symbol"), float(g.get("x", 0)),
                       float(g.get("y", 0))) for g in ds.iterfind("gates/gate")]
        # (gate, pin) -> [pads]
        self.connects: dict[tuple[str, str], list[str]] = {}
        for c in dev.iterfind("connects/connect"):
            self.connects[(c.get("gate"), c.get("pin"))] = c.get("pad", "").split()
        self.sch = spec.get("sch")
        self.angle = float(spec.get("angle", 0) or 0)
        self.board = spec.get("board")
        self.board_angle = float(spec.get("board_angle", 0) or 0)
        self.side = spec.get("side", "top")
        if self.side not in ("top", "bottom"):
            raise SpecError(f"{self.name}: side must be top or bottom")

    def symbol(self, name):
        sym = self.lib.find(f"symbols/symbol[@name='{name}']")
        if sym is None:
            raise SpecError(f"{self.name}: symbol {name} missing from library")
        return sym

    def find_pin(self, pin: str) -> tuple[str, str]:
        """'1', 'OUT' or 'A.OUT' -> (gate, pin)."""
        if "." in pin:
            gate, p = pin.split(".", 1)
            if any(g[0] == gate for g in self.gates):
                return gate, p
        hits = []
        for gname, sname, _, _ in self.gates:
            for pe in self.symbol(sname).iterfind("pin"):
                if pe.get("name") == pin:
                    hits.append((gname, pin))
        if not hits:
            names = sorted({pe.get("name") for _, s, _, _ in self.gates
                            for pe in self.symbol(s).iterfind("pin")})
            raise SpecError(f"{self.name} has no pin {pin}. Pins: "
                            f"{', '.join(names)}")
        if len(hits) > 1:
            raise SpecError(f"{self.name}.{pin} is ambiguous; use GATE.PIN, one "
                            f"of {', '.join(f'{g}.{p}' for g, p in hits)}")
        return hits[0]

    def package_el(self):
        if not self.package:
            return None
        pkg = self.lib.find(f"packages/package[@name='{self.package}']")
        if pkg is None:
            raise SpecError(f"{self.name}: package {self.package} missing")
        return pkg

    def footprint(self) -> tuple[float, float, float, float]:
        """Package-local bbox from pads, smds and placement-layer wires."""
        pkg = self.package_el()
        xs, ys = [], []
        if pkg is None:
            return (0, 0, 0, 0)
        for s in pkg.iterfind("smd"):
            x, y = float(s.get("x")), float(s.get("y"))
            dx, dy = float(s.get("dx")) / 2, float(s.get("dy")) / 2
            if s.get("rot", "R0") in ("R90", "R270"):
                dx, dy = dy, dx
            xs += [x - dx, x + dx]
            ys += [y - dy, y + dy]
        for p in pkg.iterfind("pad"):
            x, y = float(p.get("x")), float(p.get("y"))
            r = float(p.get("diameter") or 0) / 2 or float(p.get("drill")) * 0.9
            xs += [x - r, x + r]
            ys += [y - r, y + r]
        for w in pkg.iterfind("wire"):
            if w.get("layer") in ("21", "39", "51"):
                xs += [float(w.get("x1")), float(w.get("x2"))]
                ys += [float(w.get("y1")), float(w.get("y2"))]
        if not xs:
            return (0, 0, 0, 0)
        return (min(xs), min(ys), max(xs), max(ys))


def _snap(v: float) -> float:
    return round(round(v / GRID) * GRID, 4)


def _auto_sheet(parts: list[_Part]):
    """Rows of symbols, left to right, for parts without a sheet position."""
    x, y, row_h = 20.32, 160.02, 0.0
    for p in parts:
        if p.sch is not None:
            continue
        w = 30.48
        if x + w > 260:
            x, y = 20.32, y - max(row_h, 25.4)
            row_h = 0.0
        p.sch = (_snap(x), _snap(y))
        x += w
        row_h = max(row_h, 25.4)


def _auto_board(parts: list[_Part], outline: list[tuple[float, float]],
                gap: float = 1.5):
    """Shelf-pack unplaced parts inside the outline's bounding box."""
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    x0, x1, y1 = min(xs) + gap, max(xs) - gap, max(ys) - gap
    x, y, row_h = x0, y1, 0.0
    for p in parts:
        if p.board is not None or not p.package:
            continue
        bx1, by1, bx2, by2 = p.footprint()
        w, h = bx2 - bx1, by2 - by1
        if x + w > x1 and x > x0:
            x, y, row_h = x0, y - row_h - gap, 0.0
        p.board = (round(x - bx1, 3), round(y - by2, 3))
        x += w + gap
        row_h = max(row_h, h)


def _outline_points(outline) -> list[tuple[float, float]]:
    if not outline:
        raise SpecError("outline is required: {width, height} or {points}")
    if outline.get("points"):
        pts = [tuple(map(float, p)) for p in outline["points"]]
        if len(pts) < 3:
            raise SpecError("outline points need at least 3 corners")
        return pts
    w, h = float(outline["width"]), float(outline["height"])
    ox, oy = (outline.get("origin") or (0, 0))
    return [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]


def _outline_wires(outline, plain: ET.Element):
    pts = _outline_points(outline)
    r = float(outline.get("corner_radius", 0) or 0)
    if r and not outline.get("points"):
        (x0, y0), _, (x1, y1), _ = pts
        segs = [((x0 + r, y0), (x1 - r, y0), None), ((x1 - r, y0), (x1, y0 + r), 90),
                ((x1, y0 + r), (x1, y1 - r), None), ((x1, y1 - r), (x1 - r, y1), 90),
                ((x1 - r, y1), (x0 + r, y1), None), ((x0 + r, y1), (x0, y1 - r), 90),
                ((x0, y1 - r), (x0, y0 + r), None), ((x0, y0 + r), (x0 + r, y0), 90)]
    else:
        ring = core.close_ring(pts)
        segs = [(a, b, None) for a, b in zip(ring, ring[1:])]
    for (ax, ay), (bx, by), curve in segs:
        attrs = {"x1": core.fmt(ax), "y1": core.fmt(ay), "x2": core.fmt(bx),
                 "y2": core.fmt(by), "width": "0", "layer": "20"}
        if curve:
            attrs["curve"] = str(curve)
        ET.SubElement(plain, "wire", attrs)


def _pin_geometry(part: _Part, gate: str, pin: str):
    """Sheet position of a pin and the unit vector pointing out of the symbol."""
    g = next(x for x in part.gates if x[0] == gate)
    gx, gy = part.sch[0] + g[2], part.sch[1] + g[3]
    pe = part.symbol(g[1]).find(f"pin[@name='{pin}']")
    px, py = float(pe.get("x")), float(pe.get("y"))
    x, y = core.transform_point(px, py, gx, gy, part.angle)
    rot = pe.get("rot", "R0")
    mirror = rot.startswith("M")
    a = float(re.sub(r"[^0-9.]", "", rot) or 0)
    # A pin's line runs from its connection point toward the body in the
    # direction of its rotation, so "outward" is the opposite way.
    vx, vy = core.transform_point(-1.0, 0.0, 0, 0, a, mirror)
    vx, vy = core.transform_point(vx, vy, 0, 0, part.angle)
    return round(x, 4), round(y, 4), round(vx), round(vy)


def _pin_ref(ref: str) -> tuple[str, str]:
    if "." not in ref:
        raise SpecError(f"Pin '{ref}' must be PART.PIN (or PART.GATE.PIN)")
    return ref.split(".", 1)


def _layers(layers: ET.Element | None) -> ET.Element:
    if layers is not None:
        return copy.deepcopy(layers)
    el = ET.Element("layers")
    for num, name, color in _DEFAULT_LAYERS:
        ET.SubElement(el, "layer", number=str(num), name=name, color=str(color),
                      fill="1", visible="yes", active="yes")
    return el


def _classes(parent: ET.Element, classes: list[dict]):
    cls = ET.SubElement(parent, "classes")
    seen = {int(c.get("number", 0)) for c in classes}
    if 0 not in seen:
        ET.SubElement(cls, "class", number="0", name="default", width="0",
                      drill="0")
    for c in sorted(classes, key=lambda c: int(c.get("number", 0))):
        el = ET.SubElement(cls, "class", number=str(int(c.get("number", 0))),
                           name=str(c.get("name", "default")),
                           width=core.fmt(c.get("width", 0) or 0),
                           drill=core.fmt(c.get("drill", 0) or 0))
        if c.get("clearance") is not None:
            ET.SubElement(el, "clearance", attrib={
                "class": str(int(c.get("number", 0))),
                "value": core.fmt(c["clearance"])})


def build(spec: dict, libraries: dict[str, ET.Element],
          layers: ET.Element | None = None) -> dict:
    """Spec -> {'sch': xml, 'brd': xml, 'parts': [...], 'nets': [...]}.

    spec keys:
        parts:   [{name, library, device | deviceset+device, value,
                   technology?, attributes?, sch?: [x, y], angle?,
                   board?: [x, y], board_angle?, side?}]
        nets:    [{name, pins: ['R1.1', 'U1.A.OUT'], class?}]
        outline: {width, height, origin?, corner_radius?} | {points}
        classes: [{number, name, width, clearance, drill}]
    """
    parts: list[_Part] = []
    names = set()
    for ps in spec.get("parts") or []:
        if not ps.get("name"):
            raise SpecError("Every part needs a name (R1, U2, ...)")
        if ps["name"] in names:
            raise SpecError(f"Duplicate part name {ps['name']}")
        names.add(ps["name"])
        lname = ps.get("library")
        if lname not in libraries:
            raise SpecError(f"{ps['name']}: library {lname!r} not loaded. "
                            f"Loaded: {', '.join(sorted(libraries)) or 'none'}")
        if is_managed(libraries[lname]):
            raise SpecError(
                f"Library {lname} is a Fusion managed library. Fusion's "
                "importer drops its schematic, so use a classic EAGLE library "
                "(for example rcl, supply1 or led from the bundled examples).")
        parts.append(_Part(ps, libraries[lname], lname))
    if not parts:
        raise SpecError("The spec has no parts")
    by_name = {p.name: p for p in parts}

    nets = []
    pin_owner: dict[tuple[str, str, str], str] = {}
    for ns in spec.get("nets") or []:
        if not ns.get("name"):
            raise SpecError("Every net needs a name")
        refs = []
        for ref in ns.get("pins") or []:
            pname, pin = _pin_ref(ref)
            if pname not in by_name:
                raise SpecError(f"Net {ns['name']}: no part {pname}")
            gate, p = by_name[pname].find_pin(pin)
            key = (pname, gate, p)
            if key in pin_owner and pin_owner[key] != ns["name"]:
                raise SpecError(f"{ref} is on both {pin_owner[key]} and "
                                f"{ns['name']}")
            pin_owner[key] = ns["name"]
            refs.append(key)
        if not refs:
            raise SpecError(f"Net {ns['name']} has no pins")
        nets.append((ns["name"], int(ns.get("class", 0) or 0), refs))

    outline = spec.get("outline")
    _auto_sheet(parts)
    _auto_board(parts, _outline_points(outline))
    used_libs = sorted({p.lname for p in parts})

    # ---------------------------------------------------------------- .sch
    sch = ET.Element("eagle", version="9.7.0")
    d = ET.SubElement(sch, "drawing")
    ET.SubElement(d, "settings")
    ET.SubElement(d, "grid", distance="0.1", unitdist="inch", unit="inch",
                  style="lines", multiple="1", display="no", altdistance="0.01",
                  altunitdist="inch", altunit="inch")
    d.append(_layers(layers))
    s = ET.SubElement(d, "schematic")
    libs = ET.SubElement(s, "libraries")
    for lname in used_libs:
        lib = copy.deepcopy(libraries[lname])
        lib.set("name", lname)
        libs.append(lib)
    ET.SubElement(s, "attributes")
    ET.SubElement(s, "variantdefs")
    _classes(s, spec.get("classes") or [])
    pe = ET.SubElement(s, "parts")
    for p in parts:
        attrs = {"name": p.name, "library": p.lname,
                 "deviceset": p.ds.get("name"), "device": p.dev.get("name", "")}
        if p.technology:
            attrs["technology"] = p.technology
        if p.value:
            attrs["value"] = p.value
        el = ET.SubElement(pe, "part", attrs)
        for k, v in p.attributes.items():
            ET.SubElement(el, "attribute", name=k, value=v)
    sheet = ET.SubElement(ET.SubElement(s, "sheets"), "sheet")
    ET.SubElement(sheet, "plain")
    insts = ET.SubElement(sheet, "instances")
    for p in parts:
        for gname, _, gx, gy in p.gates:
            ET.SubElement(insts, "instance", part=p.name, gate=gname,
                          x=core.fmt(p.sch[0] + gx), y=core.fmt(p.sch[1] + gy),
                          **({"rot": _rot(p.angle)} if p.angle else {}))
    ET.SubElement(sheet, "busses")
    nets_el = ET.SubElement(sheet, "nets")
    for name, cls, refs in nets:
        n = ET.SubElement(nets_el, "net", name=name, attrib={"class": str(cls)})
        # One segment per pin: a short stub out of the symbol with a label.
        # Segments that share a net name are connected, so the sheet stays
        # readable with no wires crossing symbols.
        for pname, gate, pin in refs:
            x, y, vx, vy = _pin_geometry(by_name[pname], gate, pin)
            ex, ey = round(x + vx * GRID, 4), round(y + vy * GRID, 4)
            seg = ET.SubElement(n, "segment")
            ET.SubElement(seg, "pinref", part=pname, gate=gate, pin=pin)
            ET.SubElement(seg, "wire", x1=core.fmt(x), y1=core.fmt(y),
                          x2=core.fmt(ex), y2=core.fmt(ey), width="0.1524",
                          layer="91")
            lab = {"x": core.fmt(ex), "y": core.fmt(ey), "size": "1.778",
                   "layer": "95"}
            if vx < 0:
                lab["rot"] = "MR0"  # text grows away from the symbol
            ET.SubElement(seg, "label", lab)

    # ---------------------------------------------------------------- .brd
    brd = ET.Element("eagle", version="9.7.0")
    d = ET.SubElement(brd, "drawing")
    ET.SubElement(d, "settings")
    ET.SubElement(d, "grid", distance="0.1", unitdist="mm", unit="mm",
                  style="lines", multiple="1", display="no", altdistance="0.01",
                  altunitdist="mm", altunit="mm")
    d.append(_layers(layers))
    b = ET.SubElement(d, "board")
    plain = ET.SubElement(b, "plain")
    _outline_wires(outline, plain)
    blibs = ET.SubElement(b, "libraries")
    for lname in used_libs:
        bl = ET.SubElement(blibs, "library", name=lname)
        pk = libraries[lname].find("packages")
        bl.append(copy.deepcopy(pk) if pk is not None else ET.Element("packages"))
    ET.SubElement(b, "attributes")
    ET.SubElement(b, "variantdefs")
    _classes(b, spec.get("classes") or [])
    ET.SubElement(b, "designrules", name="default")
    els = ET.SubElement(b, "elements")
    placed = []
    for p in parts:
        if not p.package:
            continue  # supply symbols, frames: schematic only
        attrs = {"name": p.name, "library": p.lname, "package": p.package,
                 "value": p.value, "x": core.fmt(p.board[0]),
                 "y": core.fmt(p.board[1])}
        rot = _rot(p.board_angle, p.side == "bottom")
        if rot != "R0":
            attrs["rot"] = rot
        el = ET.SubElement(els, "element", attrs)
        for k, v in p.attributes.items():
            ET.SubElement(el, "attribute", name=k, value=v, display="off")
        placed.append({"name": p.name, "x": p.board[0], "y": p.board[1],
                       "angle": p.board_angle, "side": p.side})
    sigs = ET.SubElement(b, "signals")
    for name, cls, refs in nets:
        sg = ET.SubElement(sigs, "signal", name=name, attrib={"class": str(cls)})
        for pname, gate, pin in refs:
            part = by_name[pname]
            if not part.package:
                continue
            for pad in part.connects.get((gate, pin), []):
                ET.SubElement(sg, "contactref", element=pname, pad=pad)

    return {
        "sch": _xml(sch),
        "brd": _xml(brd),
        "parts": [{"name": p.name, "library": p.lname,
                   "device": p.ds.get("name") + p.dev.get("name", ""),
                   "package": p.package, "value": p.value,
                   "sch": list(p.sch)} for p in parts],
        "placed": placed,
        "nets": [{"name": n, "pins": [f"{a}.{c}" for a, _, c in r]}
                 for n, _, r in nets],
        "libraries": used_libs,
    }


def _xml(root: ET.Element) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE eagle SYSTEM "eagle.dtd">\n'
            + ET.tostring(root, encoding="unicode"))


def board_size(spec: dict) -> tuple[float, float]:
    pts = _outline_points(spec.get("outline"))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (max(xs) - min(xs), max(ys) - min(ys))


__all__ = ["SpecError", "build", "libraries_from_xml", "layers_from_xml",
           "list_devices", "is_managed", "board_size"]

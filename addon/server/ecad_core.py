"""
Electronics (ECAD) core: pure Python, no Fusion imports.

Everything here works on plain numbers, strings and dicts so it can run in
unit tests on any machine.  ``ecad.py`` is the thin Fusion-facing layer: it
reads the design through ``adsk.electron`` into plain dicts, calls into this
module, and sends the EAGLE command lines built here to Fusion through
``Electron.runScript``.

Sections:
    * EAGLE command builders (schematic, board, outputs)
    * Geometry (pin positions, stubs, polygons, via stitching)
    * Engineering calculators (E-series, dividers, trace width, impedance)
    * Reports (BOM, pick-and-place, netlist)
    * Design review checks

Units: every length in and out of this module is in millimetres.  Script
lines start with ``GRID MM`` so EAGLE reads coordinates as mm too.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections import defaultdict

# ======================================================================
# EAGLE command builders
# ======================================================================

# Layer numbers used by Fusion Electronics (inherited from EAGLE).
LAYERS = {
    "top": 1,
    "bottom": 16,
    "pads": 17,
    "vias": 18,
    "unrouted": 19,
    "dimension": 20,
    "tplace": 21,
    "bplace": 22,
    "torigins": 23,
    "borigins": 24,
    "tnames": 25,
    "bnames": 26,
    "tvalues": 27,
    "bvalues": 28,
    "tstop": 29,
    "bstop": 30,
    "tcream": 31,
    "bcream": 32,
    "tfinish": 33,
    "bfinish": 34,
    "tglue": 35,
    "bglue": 36,
    "ttest": 37,
    "btest": 38,
    "tkeepout": 39,
    "bkeepout": 40,
    "trestrict": 41,
    "brestrict": 42,
    "vrestrict": 43,
    "drills": 44,
    "holes": 45,
    "milling": 46,
    "measures": 47,
    "document": 48,
    "reference": 49,
    "tdocu": 51,
    "bdocu": 52,
    "nets": 91,
    "busses": 92,
    "pins": 93,
    "symbols": 94,
    "names": 95,
    "values": 96,
    "info": 97,
    "guide": 98,
}

# Inner copper layers 2..15 are addressed by number.
COPPER_LAYERS = set(range(1, 17))

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_\-.+$/#]+$")


def layer_number(layer) -> int:
    """Accept 1..255 or a name ('top', 'bottom', 'tplace', 'inner2')."""
    if isinstance(layer, bool):
        raise ValueError(f"Invalid layer {layer!r}")
    if isinstance(layer, int):
        if 1 <= layer <= 255:
            return layer
        raise ValueError(f"Layer number out of range: {layer}")
    s = str(layer).strip().lower()
    if s.isdigit():
        return layer_number(int(s))
    m = re.fullmatch(r"inner(\d+)", s)
    if m:
        n = int(m.group(1))
        if 2 <= n <= 15:
            return n
        raise ValueError(f"Inner layer must be inner2..inner15, got {layer!r}")
    if s in LAYERS:
        return LAYERS[s]
    raise ValueError(
        f"Unknown layer {layer!r}. Use a number or one of: "
        f"{', '.join(sorted(LAYERS))}, inner2..inner15"
    )


def fmt(v: float) -> str:
    """Format a number for an EAGLE command: short, no exponent."""
    if isinstance(v, bool):
        raise ValueError("Boolean is not a coordinate")
    v = float(v)
    if not math.isfinite(v):
        raise ValueError(f"Non-finite number: {v}")
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(x: float, y: float) -> str:
    return f"({fmt(x)} {fmt(y)})"


def quote(s: str) -> str:
    """Quote a name or string for EAGLE: single quotes, doubled inside."""
    s = str(s)
    if "\n" in s or "\r" in s:
        raise ValueError("Newlines are not allowed in EAGLE strings")
    return "'" + s.replace("'", "''") + "'"


def token(s: str) -> str:
    """A bare EAGLE token (device, library, layer name).  Quote if needed."""
    s = str(s)
    if not s:
        raise ValueError("Empty name")
    return s if _SAFE_TOKEN.match(s) else quote(s)


def orientation(angle: float = 0.0, mirror: bool = False, spin: bool = False) -> str:
    """EAGLE orientation flag, e.g. R90, MR180, SR45."""
    a = float(angle) % 360.0
    prefix = ("S" if spin else "") + ("M" if mirror else "")
    return f"{prefix}R{fmt(a)}"


def script(lines: list[str], grid_mm: bool = True) -> str:
    """Join command lines into a script.  Every line ends with ';'."""
    out = ["GRID MM;"] if grid_mm else []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "\n" in line or "\r" in line:
            raise ValueError(f"Command contains a newline: {line!r}")
        out.append(line if line.endswith(";") else line + ";")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- schematic


def cmd_add(
    device: str,
    library: str,
    name: str | None,
    x: float,
    y: float,
    angle: float = 0.0,
    mirror: bool = False,
    gate: str | None = None,
) -> str:
    """ADD a device from a library: ``ADD dev@lib 'R1' R90 (x y)``."""
    parts = [f"ADD {token(device)}@{token(library)}"]
    if name:
        parts.append(quote(name))
        if gate:
            parts.append(token(gate))
    parts.append(orientation(angle, mirror))
    parts.append(pt(x, y))
    return " ".join(parts)


def cmd_value(part: str, value: str) -> str:
    return f"VALUE {quote(part)} {quote(value)}"


def cmd_attribute(part: str, name: str, value: str) -> str:
    return f"ATTRIBUTE {quote(part)} {quote(name)} {quote(value)}"


def cmd_net(net: str | None, points: list[tuple[float, float]]) -> str:
    if len(points) < 2:
        raise ValueError("A net segment needs at least two points")
    head = f"NET {quote(net)} " if net else "NET "
    return head + " ".join(pt(x, y) for x, y in points)


def cmd_edit_sheet(sheet: int) -> str:
    return f"EDIT .s{int(sheet)}"


# -------------------------------------------------------------------- board


def cmd_move(name: str, x: float, y: float) -> str:
    return f"MOVE {quote(name)} {pt(x, y)}"


def cmd_rotate_abs(name: str, angle: float, mirror: bool = False) -> str:
    """Set absolute rotation (and side) with ``ROTATE =MR90 'U1'``."""
    return f"ROTATE ={orientation(angle, mirror)} {quote(name)}"


def cmd_layer(layer) -> str:
    return f"LAYER {layer_number(layer)}"


def cmd_wire(
    points: list[tuple[float, float]],
    width: float,
    signal: str | None = None,
) -> str:
    if len(points) < 2:
        raise ValueError("A wire needs at least two points")
    if width < 0:
        raise ValueError("Wire width cannot be negative")
    head = f"WIRE {quote(signal)} " if signal else "WIRE "
    return head + fmt(width) + " " + " ".join(pt(x, y) for x, y in points)


def cmd_via(
    signal: str | None,
    x: float,
    y: float,
    diameter: float | None = None,
    shape: str = "round",
    layers: str | None = None,
) -> str:
    shape = shape.lower()
    if shape not in ("round", "square", "octagon"):
        raise ValueError("Via shape must be round, square or octagon")
    parts = ["VIA"]
    if signal:
        parts.append(quote(signal))
    if diameter is not None:
        parts.append(fmt(diameter))
    parts.append(shape)
    if layers:
        if not re.fullmatch(r"\d{1,2}-\d{1,2}", layers):
            raise ValueError("Via layers must look like '1-16'")
        parts.append(layers)
    parts.append(pt(x, y))
    return " ".join(parts)


def cmd_polygon(
    signal: str | None,
    points: list[tuple[float, float]],
    width: float = 0.254,
) -> str:
    pts = close_ring(points)
    if len(pts) < 4:
        raise ValueError("A polygon needs at least three distinct corners")
    head = f"POLYGON {quote(signal)} " if signal else "POLYGON "
    return head + fmt(width) + " " + " ".join(pt(x, y) for x, y in pts)


def cmd_hole(drill: float, x: float, y: float) -> str:
    if drill <= 0:
        raise ValueError("Hole drill must be positive")
    return f"HOLE {fmt(drill)} {pt(x, y)}"


def cmd_text(text: str, x: float, y: float, angle: float = 0.0,
             mirror: bool = False) -> str:
    return f"TEXT {quote(text)} {orientation(angle, mirror)} {pt(x, y)}"


def pour_setup_lines(
    isolate: float | None = None,
    rank: int | None = None,
    thermals: bool | None = None,
    orphans: bool | None = None,
    spacing: float | None = None,
    hatched: bool = False,
) -> list[str]:
    lines = [f"CHANGE POUR {'HATCH' if hatched else 'SOLID'}"]
    if isolate is not None:
        lines.append(f"CHANGE ISOLATE {fmt(isolate)}")
    if rank is not None:
        if not 1 <= int(rank) <= 6:
            raise ValueError("Polygon rank must be 1..6")
        lines.append(f"CHANGE RANK {int(rank)}")
    if thermals is not None:
        lines.append(f"CHANGE THERMALS {'ON' if thermals else 'OFF'}")
    if orphans is not None:
        lines.append(f"CHANGE ORPHANS {'ON' if orphans else 'OFF'}")
    if spacing is not None and hatched:
        lines.append(f"CHANGE SPACING {fmt(spacing)}")
    return lines


def text_setup_lines(size: float = 1.0, ratio: int = 15,
                     font: str = "vector") -> list[str]:
    font = font.lower()
    if font not in ("vector", "proportional", "fixed"):
        raise ValueError("Font must be vector, proportional or fixed")
    if not 1 <= int(ratio) <= 31:
        raise ValueError("Text ratio must be 1..31 percent")
    return [
        f"CHANGE SIZE {fmt(size)}",
        f"CHANGE RATIO {int(ratio)}",
        f"CHANGE FONT {font.upper()}",
    ]


def outline_lines(
    points: list[tuple[float, float]] | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
    corner_radius: float = 0.0,
    origin: tuple[float, float] = (0.0, 0.0),
    line_width: float = 0.0,
) -> list[str]:
    """Board outline on layer 20 (Dimension).

    Either an explicit closed polygon (``points``) or a rectangle
    (``width_mm`` x ``height_mm``) from ``origin``, optionally with rounded
    corners drawn as WIRE arcs.
    """
    lines = [cmd_layer("dimension")]
    if points:
        ring = close_ring(points)
        if len(ring) < 4:
            raise ValueError("Outline needs at least three corners")
        lines.append(cmd_wire(ring, line_width))
        return lines
    if not width_mm or not height_mm or width_mm <= 0 or height_mm <= 0:
        raise ValueError("Give either points or a positive width_mm and height_mm")
    x0, y0 = origin
    w, h, r = float(width_mm), float(height_mm), float(corner_radius)
    if r <= 0:
        lines.append(
            cmd_wire(
                [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)],
                line_width,
            )
        )
        return lines
    if r * 2 > min(w, h):
        raise ValueError("Corner radius is larger than half the board side")
    lw = fmt(line_width)
    # Straight edges
    edges = [
        [(x0 + r, y0), (x0 + w - r, y0)],
        [(x0 + w, y0 + r), (x0 + w, y0 + h - r)],
        [(x0 + w - r, y0 + h), (x0 + r, y0 + h)],
        [(x0, y0 + h - r), (x0, y0 + r)],
    ]
    for e in edges:
        lines.append(cmd_wire(e, line_width))
    # Corner arcs: WIRE width (start) @+90 (end) -> 90 degree counter-clockwise arc
    arcs = [
        ((x0 + w - r, y0), (x0 + w, y0 + r)),
        ((x0 + w, y0 + h - r), (x0 + w - r, y0 + h)),
        ((x0 + r, y0 + h), (x0, y0 + h - r)),
        ((x0, y0 + r), (x0 + r, y0)),
    ]
    for (sx, sy), (ex, ey) in arcs:
        lines.append(f"WIRE {lw} {pt(sx, sy)} +90 {pt(ex, ey)}")
    return lines


# ======================================================================
# Geometry
# ======================================================================


def close_ring(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in points]
    if not pts:
        return pts
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def transform_point(
    px: float,
    py: float,
    ox: float,
    oy: float,
    angle: float = 0.0,
    mirror: bool = False,
) -> tuple[float, float]:
    """Symbol/package-local point to sheet/board coordinates.

    EAGLE applies mirror (about the Y axis) first, then rotation
    counter-clockwise, then translation.
    """
    if mirror:
        px = -px
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    return (ox + px * c - py * s, oy + px * s + py * c)


_PIN_DIR = {"R0": (1, 0), "R90": (0, 1), "R180": (-1, 0), "R270": (0, -1)}


def stub_end(
    pin_x: float,
    pin_y: float,
    inst_x: float,
    inst_y: float,
    length: float = 2.54,
) -> tuple[float, float]:
    """Where a short net stub from a pin should end.

    Points away from the symbol origin along the dominant axis, so stubs
    leave the symbol instead of crossing it.
    """
    dx, dy = pin_x - inst_x, pin_y - inst_y
    if abs(dx) >= abs(dy):
        return (pin_x + math.copysign(length, dx if dx else 1.0), pin_y)
    return (pin_x, pin_y + math.copysign(length, dy))


def point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    vv = vx * vx + vy * vy
    t = 0.0 if vv == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / vv))
    cx, cy = ax + t * vx, ay + t * vy
    return math.hypot(px - cx, py - cy)


def distance_to_polygon_edge(x: float, y: float,
                             poly: list[tuple[float, float]]) -> float:
    ring = close_ring(poly)
    return min(
        _seg_dist(x, y, *ring[i], *ring[i + 1]) for i in range(len(ring) - 1)
    )


def stitching_points(
    region: list[tuple[float, float]],
    pitch: float,
    edge_clearance: float = 1.0,
    obstacles: list[tuple[float, float, float]] | None = None,
    stagger: bool = True,
) -> list[tuple[float, float]]:
    """Grid of via positions inside ``region``.

    ``obstacles`` are (x, y, radius) circles to keep clear of (pads, other
    vias, holes); ``edge_clearance`` keeps vias off the region edge.
    """
    if pitch <= 0:
        raise ValueError("Pitch must be positive")
    ring = close_ring(region)
    if len(ring) < 4:
        raise ValueError("Region needs at least three corners")
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    obstacles = obstacles or []
    out = []
    row = 0
    y = min(ys) + edge_clearance
    while y <= max(ys) - edge_clearance + 1e-9:
        x = min(xs) + edge_clearance + (pitch / 2 if stagger and row % 2 else 0)
        while x <= max(xs) - edge_clearance + 1e-9:
            if (
                point_in_polygon(x, y, ring[:-1])
                and distance_to_polygon_edge(x, y, ring) >= edge_clearance
                and all(math.hypot(x - ox, y - oy) >= r for ox, oy, r in obstacles)
            ):
                out.append((round(x, 4), round(y, 4)))
            x += pitch
        y += pitch
        row += 1
    return out


def bbox_overlap(a: tuple, b: tuple, margin: float = 0.0) -> bool:
    """Boxes are (x1, y1, x2, y2)."""
    return not (
        a[2] + margin <= b[0]
        or b[2] + margin <= a[0]
        or a[3] + margin <= b[1]
        or b[3] + margin <= a[1]
    )


# ======================================================================
# Engineering calculators
# ======================================================================

E_SERIES = {
    "E6": [1.0, 1.5, 2.2, 3.3, 4.7, 6.8],
    "E12": [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2],
    "E24": [
        1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
    ],
}


def _e_decade(n: int) -> list[float]:
    # E48/E96/E192 follow the formula, rounded to 3 significant figures.
    vals = []
    for i in range(n):
        v = round(10 ** (i / n), 2)
        vals.append(v)
    # Known exception in E192/E96 tables: 9.20 instead of 9.19.
    return [9.2 if abs(v - 9.19) < 1e-9 else v for v in vals]


for _n in (48, 96, 192):
    E_SERIES[f"E{_n}"] = _e_decade(_n)


def e_series_values(series: str, lo: float, hi: float) -> list[float]:
    base = E_SERIES.get(series.upper())
    if base is None:
        raise ValueError(f"Unknown series {series!r}; use {', '.join(E_SERIES)}")
    if lo <= 0 or hi <= 0 or hi < lo:
        raise ValueError("Range must be positive and lo <= hi")
    out = []
    for d in range(math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1):
        for b in base:
            v = round(b * 10**d, 12)
            if lo * (1 - 1e-9) <= v <= hi * (1 + 1e-9):
                out.append(v)
    return sorted(set(out))


def nearest_e(value: float, series: str = "E24") -> dict:
    """Nearest preferred value, plus the one below and above."""
    if value <= 0:
        raise ValueError("Value must be positive")
    vals = e_series_values(series, value / 20, value * 20)
    below = max((v for v in vals if v <= value * (1 + 1e-12)), default=None)
    above = min((v for v in vals if v >= value * (1 - 1e-12)), default=None)
    best = min(vals, key=lambda v: abs(math.log(v / value)))
    return {
        "value": value,
        "series": series.upper(),
        "nearest": best,
        "below": below,
        "above": above,
        "error_pct": round((best - value) / value * 100, 3),
    }


_SI = [
    (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""),
    (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p"),
]


def si(value: float, unit: str = "") -> str:
    """Engineering notation: 4700 -> '4.7k', 1e-7 -> '100n'."""
    if value == 0:
        return f"0{unit}"
    for mult, prefix in _SI:
        if abs(value) >= mult * 0.9999999:
            n = value / mult
            s = f"{n:.3g}"
            return f"{s}{prefix}{unit}"
    return f"{value:.3g}{unit}"


_SI_IN = {"T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "K": 1e3, "R": 1, "": 1,
          "m": 1e-3, "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12}


def parse_si(s) -> float:
    """'4k7' -> 4700, '10k' -> 10000, '100n' -> 1e-7, '2R2' -> 2.2, '0.1uF'."""
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace(" ", "")
    t = re.sub(r"(?i)(ohms?|Ω|F|H|V|A|W|Hz)$", "", t)
    m = re.fullmatch(r"([0-9]*)([TGMkKRmuµnp])([0-9]+)", t)
    if m:  # RKM code: 4k7, 2R2
        return float(f"{m.group(1) or 0}.{m.group(3)}") * _SI_IN[m.group(2)]
    m = re.fullmatch(r"([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?)([TGMkKRmuµnp]?)", t)
    if not m:
        raise ValueError(f"Cannot read value {s!r}")
    return float(m.group(1)) * _SI_IN[m.group(2)]


def divider(
    vin: float,
    vout: float,
    series: str = "E24",
    r_total_min: float = 1e3,
    r_total_max: float = 1e6,
    top: float | None = None,
) -> dict:
    """Best resistor pair for vout = vin * Rb / (Rt + Rb).

    Searches the preferred-value series within a total-resistance window,
    or with a fixed top resistor.  Returns the best few pairs.
    """
    if not 0 < vout < vin:
        raise ValueError("Need 0 < vout < vin")
    ratio = vout / vin
    vals = e_series_values(series, 1.0, 10e6)
    cands = []
    tops = [top] if top else vals
    for rt in tops:
        for rb in vals:
            tot = rt + rb
            if not top and not (r_total_min <= tot <= r_total_max):
                continue
            v = vin * rb / tot
            cands.append((abs(v - vout), rt, rb, v))
    if not cands:
        raise ValueError("No pair in range; widen r_total_min/max")
    cands.sort(key=lambda c: (c[0], c[1] + c[2]))
    best = []
    for err, rt, rb, v in cands[:5]:
        best.append({
            "r_top": rt, "r_bottom": rb,
            "r_top_si": si(rt, "Ω"), "r_bottom_si": si(rb, "Ω"),
            "vout": round(v, 6),
            "error_pct": round((v - vout) / vout * 100, 4),
            "current_uA": round(vin / (rt + rb) * 1e6, 3),
            "thevenin_ohm": round(rt * rb / (rt + rb), 3),
        })
    return {"vin": vin, "vout_target": vout, "ratio": ratio, "series": series,
            "best": best}


def trace_width(
    current_a: float,
    temp_rise_c: float = 10.0,
    copper_oz: float = 1.0,
    layer: str = "external",
    length_mm: float | None = None,
    ambient_c: float = 25.0,
) -> dict:
    """IPC-2221 trace width for a current and temperature rise.

    I = k * dT^0.44 * A^0.725, A in mil^2; k = 0.048 external, 0.024
    internal.  Conservative for most boards; IPC-2152 gives narrower
    traces when there is copper nearby.
    """
    if current_a <= 0 or temp_rise_c <= 0 or copper_oz <= 0:
        raise ValueError("Current, temperature rise and copper weight must be > 0")
    k = 0.048 if layer == "external" else 0.024
    area_mil2 = (current_a / (k * temp_rise_c**0.44)) ** (1 / 0.725)
    thickness_mil = 1.378 * copper_oz
    width_mil = area_mil2 / thickness_mil
    width_mm = width_mil * 0.0254
    out = {
        "current_a": current_a,
        "temp_rise_c": temp_rise_c,
        "copper_oz": copper_oz,
        "layer": layer,
        "width_mm": round(width_mm, 3),
        "width_mil": round(width_mil, 1),
        "cross_section_mil2": round(area_mil2, 1),
        "standard": "IPC-2221",
    }
    if length_mm:
        rho = 1.72e-8 * (1 + 0.00393 * (ambient_c + temp_rise_c - 20))
        area_m2 = (width_mm * 1e-3) * (thickness_mil * 25.4e-6)
        r = rho * (length_mm * 1e-3) / area_m2
        out["resistance_mohm"] = round(r * 1e3, 3)
        out["voltage_drop_mv"] = round(r * current_a * 1e3, 2)
        out["power_loss_mw"] = round(r * current_a**2 * 1e3, 2)
    return out


def via_current(
    drill_mm: float,
    plating_um: float = 25.0,
    temp_rise_c: float = 10.0,
    length_mm: float = 1.6,
) -> dict:
    """Approximate via current capacity (barrel as an internal conductor)."""
    if drill_mm <= 0 or plating_um <= 0:
        raise ValueError("Drill and plating must be > 0")
    d_outer = drill_mm + 2 * plating_um / 1000
    area_mm2 = math.pi / 4 * (d_outer**2 - drill_mm**2)
    area_mil2 = area_mm2 / (0.0254**2)
    current = 0.048 * temp_rise_c**0.44 * area_mil2**0.725
    rho = 1.72e-8
    r = rho * (length_mm * 1e-3) / (area_mm2 * 1e-6)
    return {
        "drill_mm": drill_mm,
        "plating_um": plating_um,
        "current_a": round(current, 2),
        "resistance_mohm": round(r * 1e3, 3),
        "note": "Approximation; use several vias for high current paths.",
    }


def microstrip_impedance(
    width_mm: float,
    height_mm: float,
    er: float = 4.4,
    thickness_mm: float = 0.035,
) -> dict:
    """IPC-2141 surface microstrip, valid roughly 0.1 < w/h < 2.0."""
    if min(width_mm, height_mm, er, thickness_mm) <= 0:
        raise ValueError("All dimensions must be > 0")
    z0 = 87 / math.sqrt(er + 1.41) * math.log(
        5.98 * height_mm / (0.8 * width_mm + thickness_mm)
    )
    return {
        "z0_ohm": round(z0, 2),
        "width_mm": width_mm,
        "height_mm": height_mm,
        "er": er,
        "valid": 0.1 < width_mm / height_mm < 2.0,
        "standard": "IPC-2141 (estimate, ~10%)",
    }


def microstrip_width_for(z0: float, height_mm: float, er: float = 4.4,
                         thickness_mm: float = 0.035) -> dict:
    lo, hi = 0.01, 20.0
    for _ in range(80):
        mid = (lo + hi) / 2
        z = microstrip_impedance(mid, height_mm, er, thickness_mm)["z0_ohm"]
        if z > z0:
            lo = mid
        else:
            hi = mid
    w = (lo + hi) / 2
    return {"z0_target": z0, "width_mm": round(w, 4), "height_mm": height_mm,
            "er": er, "standard": "IPC-2141 (estimate, ~10%)"}


def led_resistor(supply_v: float, led_vf: float, current_ma: float,
                 series: str = "E24") -> dict:
    if supply_v <= led_vf:
        raise ValueError("Supply must exceed LED forward voltage")
    r = (supply_v - led_vf) / (current_ma / 1000)
    pick = e_series_values(series, r, r * 2)[0]
    i = (supply_v - led_vf) / pick
    return {"r_exact": round(r, 2), "r_pick": pick, "r_pick_si": si(pick, "Ω"),
            "current_ma": round(i * 1000, 3),
            "power_mw": round(i * i * pick * 1000, 2)}


def rc_filter(r_ohm: float | None = None, c_f: float | None = None,
              fc_hz: float | None = None, series: str = "E24") -> dict:
    """Give any two of R, C, fc; returns the third (fc = 1 / 2piRC)."""
    given = sum(v is not None for v in (r_ohm, c_f, fc_hz))
    if given != 2:
        raise ValueError("Give exactly two of r_ohm, c_f, fc_hz")
    if fc_hz is None:
        fc = 1 / (2 * math.pi * r_ohm * c_f)
        return {"r_ohm": r_ohm, "c_f": c_f, "fc_hz": round(fc, 4),
                "tau_s": r_ohm * c_f}
    if r_ohm is None:
        r = 1 / (2 * math.pi * fc_hz * c_f)
        n = nearest_e(r, series)
        return {"r_exact": r, "r_pick": n["nearest"],
                "fc_with_pick": 1 / (2 * math.pi * n["nearest"] * c_f)}
    c = 1 / (2 * math.pi * fc_hz * r_ohm)
    n = nearest_e(c, "E12")
    return {"c_exact": c, "c_pick": n["nearest"], "c_pick_si": si(n["nearest"], "F"),
            "fc_with_pick": 1 / (2 * math.pi * r_ohm * n["nearest"])}


def resistor_power(r_ohm: float, v: float | None = None,
                   i: float | None = None) -> dict:
    if (v is None) == (i is None):
        raise ValueError("Give exactly one of v or i")
    p = v * v / r_ohm if v is not None else i * i * r_ohm
    sizes = [("0201", 0.05), ("0402", 0.063), ("0603", 0.1), ("0805", 0.125),
             ("1206", 0.25), ("1210", 0.5), ("2010", 0.75), ("2512", 1.0)]
    ok = [s for s, rating in sizes if rating >= 2 * p]
    return {"power_w": p, "derated_2x_min_w": 2 * p,
            "smallest_package_at_50pct": ok[0] if ok else None}


CALCULATORS = {
    "trace_width": trace_width,
    "via_current": via_current,
    "divider": divider,
    "nearest_e": nearest_e,
    "e_series": lambda series="E24", lo=1.0, hi=10.0: {
        "values": e_series_values(series, lo, hi)},
    "microstrip_impedance": microstrip_impedance,
    "microstrip_width_for": microstrip_width_for,
    "led_resistor": led_resistor,
    "rc_filter": rc_filter,
    "resistor_power": resistor_power,
    "parse_value": lambda value: {"value": parse_si(value)},
}


def calculate(kind: str, **kwargs) -> dict:
    fn = CALCULATORS.get(kind)
    if fn is None:
        raise ValueError(f"Unknown calculator {kind!r}; use {', '.join(CALCULATORS)}")
    return fn(**kwargs)


# ======================================================================
# Reports
# ======================================================================

_REF_RE = re.compile(r"^([A-Za-z_]+)(\d*)(.*)$")


def ref_sort_key(name: str):
    m = _REF_RE.match(name or "")
    if not m:
        return (name, 0, "")
    return (m.group(1).upper(), int(m.group(2) or 0), m.group(3))


def bom(parts: list[dict], group: bool = True,
        attribute_columns: list[str] | None = None) -> dict:
    """Bill of materials from part dicts.

    Each part: name, value, device, package, attributes (dict),
    populate (bool, default True).  Parts with no package (frames, supply
    symbols) are skipped.  Grouped rows join identical value+package+MPN.
    """
    attribute_columns = attribute_columns or ["MPN", "MANUFACTURER"]
    rows = []
    skipped = []
    for p in parts:
        if not p.get("package"):
            skipped.append(p.get("name"))
            continue
        if p.get("populate") is False:
            skipped.append(p.get("name"))
            continue
        attrs = {k.upper(): v for k, v in (p.get("attributes") or {}).items()}
        rows.append({
            "ref": p["name"],
            "value": p.get("value") or "",
            "device": p.get("device") or "",
            "package": p.get("package") or "",
            **{c: attrs.get(c.upper(), "") for c in attribute_columns},
        })
    rows.sort(key=lambda r: ref_sort_key(r["ref"]))
    if group:
        groups: dict = {}
        for r in rows:
            key = (r["value"], r["package"], r["device"],
                   *(r[c] for c in attribute_columns))
            g = groups.setdefault(key, {**r, "refs": [], "qty": 0})
            g["refs"].append(r["ref"])
            g["qty"] += 1
        out_rows = []
        for g in groups.values():
            g.pop("ref", None)
            g["refs"] = ", ".join(g["refs"])
            out_rows.append(g)
        out_rows.sort(key=lambda g: ref_sort_key(g["refs"].split(",")[0]))
        cols = ["qty", "refs", "value", "package", "device", *attribute_columns]
    else:
        out_rows = rows
        cols = ["ref", "value", "package", "device", *attribute_columns]
    missing_mpn = [
        r["ref"] for r in rows if "MPN" in attribute_columns and not r["MPN"]
    ]
    return {
        "columns": cols,
        "rows": out_rows,
        "csv": to_csv(cols, out_rows),
        "line_items": len(out_rows),
        "placements": len(rows),
        "skipped_no_package_or_dnp": skipped,
        "missing_mpn": missing_mpn,
    }


def pick_and_place(elements: list[dict], origin: tuple[float, float] = (0, 0),
                   fmt_style: str = "jlcpcb") -> dict:
    """Centroid file from board element dicts.

    Each element: name, value, package, x, y (mm), angle, mirror (bool,
    True = bottom side), smd (bool, optional), populate.
    """
    ox, oy = origin
    rows = []
    for e in elements:
        if e.get("populate") is False:
            continue
        if e.get("smd") is False:
            continue
        side = "Bottom" if e.get("mirror") else "Top"
        rows.append({
            "Designator": e["name"],
            "Val": e.get("value") or "",
            "Package": e.get("package") or "",
            "Mid X": f"{e['x'] - ox:.4f}mm",
            "Mid Y": f"{e['y'] - oy:.4f}mm",
            "Rotation": fmt(float(e.get("angle") or 0) % 360),
            "Layer": side,
        })
    rows.sort(key=lambda r: ref_sort_key(r["Designator"]))
    cols = ["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"]
    if fmt_style == "generic":
        cols = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation", "Val", "Package"]
    return {"columns": cols, "rows": rows, "csv": to_csv(cols, rows),
            "count": len(rows),
            "top": sum(r["Layer"] == "Top" for r in rows),
            "bottom": sum(r["Layer"] == "Bottom" for r in rows)}


def netlist_text(nets: list[dict]) -> str:
    """'NET: PART.PIN PART.PIN' lines, sorted."""
    lines = []
    for n in sorted(nets, key=lambda n: n["name"]):
        pins = sorted(f"{c['part']}.{c['pin']}" for c in n.get("pins", []))
        lines.append(f"{n['name']}: {' '.join(pins)}")
    return "\n".join(lines) + ("\n" if lines else "")


def to_csv(cols: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore",
                       lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def summarize_errors(errors: list[dict]) -> dict:
    """Group DRC/ERC error dicts by code/description."""
    by = defaultdict(list)
    for e in errors:
        key = e.get("description") or e.get("code") or "unknown"
        by[key].append(e)
    groups = [
        {"description": k, "count": len(v),
         "examples": [{kk: e.get(kk) for kk in ("x", "y", "layer", "signature",
                                                "state", "sheet")
                       if e.get(kk) is not None} for e in v[:5]]}
        for k, v in by.items()
    ]
    groups.sort(key=lambda g: -g["count"])
    active = [e for e in errors if str(e.get("state", "")).lower()
              not in ("approved", "1")]
    return {"total": len(errors), "active": len(active), "groups": groups}


# ======================================================================
# Design review
# ======================================================================

_POWER_RE = re.compile(
    r"^(\+?\d+V\d*|\+?V(CC|DD|IN|BAT|BUS|SYS|MOT|PWR)\w*|VBUS|VSYS|VMOT|PWR\w*|"
    r"\+\d+V\w*|\d+V\d*\w*|VCC\w*|VDD\w*|VIN\w*)$",
    re.IGNORECASE,
)
_GND_RE = re.compile(r"^(A|D|P|CH)?GND\w*$|^VSS\w*$|^0V$", re.IGNORECASE)


def is_power_net(name: str) -> bool:
    return bool(_POWER_RE.match(name or ""))


def is_ground_net(name: str) -> bool:
    return bool(_GND_RE.match(name or ""))


def review(
    parts: list[dict] | None = None,
    nets: list[dict] | None = None,
    elements: list[dict] | None = None,
    signals: list[dict] | None = None,
    outline: list[tuple[float, float]] | None = None,
    classes: list[dict] | None = None,
    errors: list[dict] | None = None,
    power_currents: dict[str, float] | None = None,
    decoupling_max_mm: float = 3.0,
) -> dict:
    """Automated design review over plain dicts.

    Every finding: {severity: error|warning|info, check, message, refs}.
    ``power_currents`` maps net name -> amps so track widths can be
    checked against IPC-2221 (10 C rise, 1 oz external).
    """
    findings: list[dict] = []

    def add(sev, check, msg, refs=None):
        findings.append({"severity": sev, "check": check, "message": msg,
                         "refs": refs or []})

    parts = parts or []
    nets = nets or []
    elements = elements or []
    signals = signals or []

    # ---- schematic
    for p in parts:
        if not p.get("package"):
            continue
        prefix = ref_sort_key(p["name"])[0]
        if prefix in ("R", "C", "L", "F", "FB", "D", "LED", "Y", "X") and not (
            p.get("value") or ""
        ).strip():
            add("error", "missing_value", f"{p['name']} has no value", [p["name"]])
        if (p.get("value") or "").strip().upper() == (p.get("device") or "").upper():
            if prefix in ("R", "C", "L"):
                add("warning", "default_value",
                    f"{p['name']} value is still the device name", [p["name"]])
        attrs = {k.upper(): v for k, v in (p.get("attributes") or {}).items()}
        if not attrs.get("MPN") and prefix not in ("TP", "FID", "H", "MH", "J"):
            add("info", "missing_mpn", f"{p['name']} has no MPN attribute",
                [p["name"]])
        if "?" in p["name"]:
            add("warning", "unnamed_part", f"{p['name']} was never annotated",
                [p["name"]])

    names = defaultdict(int)
    for p in parts:
        names[p["name"]] += 1
    for n, c in names.items():
        if c > 1:
            add("error", "duplicate_ref", f"Reference {n} is used {c} times", [n])

    for n in nets:
        pins = n.get("pins", [])
        if len(pins) == 1:
            add("warning", "single_pin_net",
                f"Net {n['name']} connects only {pins[0]['part']}.{pins[0]['pin']}",
                [pins[0]["part"]])
        if len(pins) == 0:
            add("info", "empty_net", f"Net {n['name']} has no pins", [])
        if re.fullmatch(r"N\$\d+", n["name"]) and len(pins) > 2:
            add("info", "auto_named_net",
                f"Net {n['name']} ({len(pins)} pins) has an automatic name; "
                "name it for readable outputs", [])

    # ---- board
    if elements:
        if outline:
            ring = close_ring(outline)
            for e in elements:
                if not point_in_polygon(e["x"], e["y"], ring[:-1]):
                    add("error", "outside_outline",
                        f"{e['name']} centre ({e['x']:.2f}, {e['y']:.2f}) is "
                        "outside the board outline", [e["name"]])
        else:
            add("error", "no_outline", "Board has no outline on layer 20", [])

        boxes = [(e["name"], e["bbox"], e.get("mirror", False))
                 for e in elements if e.get("bbox")]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                (na, ba, sa), (nb, bb, sb) = boxes[i], boxes[j]
                if sa == sb and bbox_overlap(ba, bb):
                    add("warning", "courtyard_overlap",
                        f"{na} and {nb} overlap on the "
                        f"{'bottom' if sa else 'top'} side", [na, nb])

        # Decoupling: every small cap on a power net should sit near an IC
        # pin on the same net.
        by_name = {e["name"]: e for e in elements}
        net_parts = defaultdict(set)
        for n in nets:
            for c in n.get("pins", []):
                net_parts[n["name"]].add(c["part"])
        for net, members in net_parts.items():
            if not is_power_net(net):
                continue
            ics = [m for m in members if ref_sort_key(m)[0] in ("U", "IC")]
            caps = [m for m in members if ref_sort_key(m)[0] == "C"]
            if not ics:
                continue
            for c in caps:
                ce = by_name.get(c)
                if not ce:
                    continue
                dists = [math.hypot(ce["x"] - by_name[u]["x"],
                                    ce["y"] - by_name[u]["y"])
                         for u in ics if u in by_name]
                if dists and min(dists) > decoupling_max_mm * 3:
                    add("info", "decoupling_distance",
                        f"{c} on {net} is {min(dists):.1f} mm from the nearest IC "
                        "centre; decoupling caps belong next to the power pin",
                        [c])

    for s in signals:
        if s.get("unrouted", 0) > 0:
            add("error", "unrouted",
                f"Signal {s['name']} has {s['unrouted']} unrouted connection(s)",
                [])
        if power_currents and s["name"] in power_currents:
            need = trace_width(power_currents[s["name"]])["width_mm"]
            narrow = [w for w in s.get("track_widths", []) if w + 1e-6 < need]
            if narrow and not s.get("has_pour"):
                add("error", "track_too_narrow",
                    f"Signal {s['name']} carries {power_currents[s['name']]} A and "
                    f"needs {need} mm (IPC-2221, 10 C rise, 1 oz); narrowest "
                    f"track is {min(narrow):.3f} mm", [])
        if is_ground_net(s["name"]) and not s.get("has_pour") and elements:
            add("info", "no_ground_pour",
                f"{s['name']} has no copper pour; most boards want a ground plane",
                [])

    if errors:
        summary = summarize_errors(errors)
        if summary["active"]:
            add("error", "check_errors",
                f"{summary['active']} DRC/ERC error(s) not approved", [])

    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["check"]))
    counts = {k: sum(f["severity"] == k for f in findings) for k in order}
    return {"counts": counts, "findings": findings,
            "passed": counts["error"] == 0}

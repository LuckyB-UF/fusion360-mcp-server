"""
MCP tool definitions for Fusion Electronics (schematic + PCB).

The add-in reads designs through ``adsk.electron`` (read-only in Fusion's
official API) and changes them by running EAGLE command scripts through
Fusion's ``Electron.runScript`` text command.  Every changing tool reads
the design back afterwards and reports what actually changed.

New circuits go in through ``ecad_build_design``: EAGLE's ADD does not work
from code in Fusion, so the add-in writes the whole design as EAGLE XML and
imports it.  Edit the spec and build again to change the circuit; then lay
out and finish the board with the editing tools.

All lengths are millimetres.  Coordinates are sheet or board coordinates.
"""

from collections.abc import Callable

from ._flags import DESTRUCTIVE, IDEMPOTENT, READ_ONLY

TOOLSET = "electronics"
SUMMARY = (
    "Fusion Electronics schematic + PCB (ecad_*): build, edit, check, "
    "export; lengths in mm"
)

_XY = {"type": "number", "description": "mm"}

_POINTS = {
    "type": "array",
    "minItems": 2,
    "items": {
        "type": "array",
        "minItems": 2,
        "maxItems": 2,
        "items": {"type": "number"},
    },
    "description": "List of [x, y] points in mm",
}

_LAYER = {
    "description": (
        "Layer number or name: top, bottom, inner2..inner15, tplace, bplace, "
        "dimension, trestrict, brestrict, vrestrict, tdocu, bdocu, milling"
    ),
    "oneOf": [{"type": "integer"}, {"type": "string"}],
}

_PATH = {"type": "string", "description": "Output file path on the Fusion PC"}

TOOLS: list[dict] = [
    # ── design / session ─────────────────────────────────────────────
    {
        "name": "ecad_new_design",
        "title": "New Electronics Design",
        "description": (
            "Create a new, empty Fusion Electronics design (schematic + PCB) "
            "and make it active. Nothing is saved until you call "
            "ecad_save_design."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "with_board": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also create the PCB now",
                },
            },
        },
    },
    {
        "name": "ecad_open_editor",
        "title": "Open Schematic or PCB Editor",
        "description": (
            "Switch the active electronics design to the schematic or the 2D "
            "PCB editor. Most commands switch automatically; use this before "
            "ecad_command when the editor matters."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["editor"],
            "properties": {
                "editor": {"type": "string", "enum": ["schematic", "board"]},
                "sheet": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Schematic sheet number",
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
    {
        "name": "ecad_save_design",
        "title": "Save Electronics Design",
        "description": (
            "Save the active electronics design. Only call when the user has "
            "asked to keep the changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Version description",
                },
                "milestone": {
                    "type": "boolean",
                    "default": False,
                    "description": "Save as a named milestone",
                },
            },
        },
    },
    {
        "name": "ecad_get_design",
        "title": "Get Electronics Design Overview",
        "description": (
            "Overview of the active electronics design: names, sheets, part, "
            "net, element and signal counts, board size, layers in use, net "
            "classes, libraries, grid, and whether DRC/ERC have been run."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": READ_ONLY,
    },
    # ── read ─────────────────────────────────────────────────────────
    {
        "name": "ecad_list_parts",
        "title": "List Schematic Parts",
        "description": (
            "Schematic parts with value, device, package, library, attributes "
            "and where each gate sits (sheet, x, y, angle)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Regex on part name or value, e.g. '^R' or '10k'",
                },
                "include_pins": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also list every pin with its net and position",
                },
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "ecad_list_nets",
        "title": "List Nets",
        "description": "Schematic nets with the PART.PIN list on each.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Regex on net name"},
                "netlist_text": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also return a sorted 'NET: P.1 P.2' text block",
                },
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "ecad_list_elements",
        "title": "List Board Elements",
        "description": (
            "Placed board components: position, rotation, side, locked, "
            "package, value and footprint bounding box."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Regex on element name"},
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "ecad_list_signals",
        "title": "List Board Signals",
        "description": (
            "Board signals (routed nets): net class, connections, unrouted "
            "airwires, track widths and length per layer, vias, and pours."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Regex on signal name"},
                "unrouted_only": {"type": "boolean", "default": False},
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "ecad_search_library",
        "title": "Search Part Libraries",
        "description": (
            "Find devices for ecad_build_design in classic EAGLE libraries: "
            "the ones bundled with Fusion (rcl, supply1, pinhead, diode, led, "
            "linear, ...) or .lbr/.sch files you name. Returns library, "
            "device full name, package, gates and pin names."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Regex on device name, package or description",
                },
                "library": {"type": "string", "description": "Limit to one library"},
                "library_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Classic EAGLE .lbr, .sch or .brd files on the Fusion PC "
                        "(their libraries replace the bundled ones)"
                    ),
                },
                "limit": {"type": "integer", "default": 40, "minimum": 1},
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "ecad_build_design",
        "title": "Build Electronics Design",
        "description": (
            "Create a new electronics design (schematic + PCB) from a full "
            "spec: parts from classic EAGLE libraries, nets, board outline, "
            "net classes, and optional board positions. The way to put a "
            "circuit into Fusion; to change the circuit, edit the spec and "
            "build again. Each net pin gets a short labelled stub on the "
            "schematic; parts without a position are laid out automatically. "
            "Reads the result back and reports anything missing. Takes "
            "10-30 s."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["parts", "outline"],
            "properties": {
                "name": {"type": "string", "description": "Design file name"},
                "output_dir": {
                    "type": "string",
                    "description": (
                        "Folder on the Fusion PC to keep the generated .sch "
                        "and .brd in (default: a new temp folder). The paths "
                        "come back either way."
                    ),
                },
                "parts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "library", "device"],
                        "properties": {
                            "name": {"type": "string", "description": "R1, U2, ..."},
                            "library": {"type": "string", "description": "e.g. rcl"},
                            "device": {
                                "type": "string",
                                "description": (
                                    "Full device name (R-EU_R0603), or the "
                                    "package variant when deviceset is given"
                                ),
                            },
                            "deviceset": {"type": "string"},
                            "technology": {"type": "string"},
                            "value": {"type": "string"},
                            "attributes": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                                "description": "MPN, MANUFACTURER, ...",
                            },
                            "sch": {**_POINTS["items"],
                                    "description": "Schematic [x, y] mm"},
                            "angle": {"type": "number",
                                      "description": "Schematic angle, 90° steps"},
                            "board": {**_POINTS["items"],
                                      "description": "Board [x, y] mm"},
                            "board_angle": {"type": "number"},
                            "side": {"type": "string", "enum": ["top", "bottom"]},
                        },
                    },
                },
                "nets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "pins"],
                        "properties": {
                            "name": {"type": "string"},
                            "pins": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "PART.PIN, or PART.GATE.PIN",
                            },
                            "class": {"type": "integer", "minimum": 0},
                        },
                    },
                },
                "outline": {
                    "type": "object",
                    "description": (
                        "{width, height, origin?, corner_radius?} or "
                        "{points: [[x, y], ...]}"
                    ),
                },
                "classes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["number", "name"],
                        "properties": {
                            "number": {"type": "integer", "minimum": 0},
                            "name": {"type": "string"},
                            "width": {"type": "number"},
                            "clearance": {"type": "number"},
                            "drill": {"type": "number"},
                        },
                    },
                },
                "library_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Classic EAGLE library files (default: bundled)",
                },
            },
        },
    },
    {
        "name": "ecad_render",
        "title": "Render Schematic or Board",
        "description": (
            "Picture of the schematic or board as a PNG so you can check "
            "placement, routing and silkscreen. Choose a layer preset or a "
            "layer list."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "editor": {
                    "type": "string",
                    "enum": ["schematic", "board"],
                    "default": "board",
                },
                "sheet": {"type": "integer", "minimum": 1},
                "preset": {
                    "type": "string",
                    "enum": ["all", "top", "bottom", "copper", "silk", "outline"],
                    "default": "all",
                },
                "layers": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                    "description": "Overrides preset",
                },
                "dpi": {"type": "integer", "minimum": 50, "maximum": 1200,
                        "default": 300},
                "monochrome": {"type": "boolean", "default": False},
            },
        },
        "annotations": READ_ONLY,
    },
    # ── checks ───────────────────────────────────────────────────────
    {
        "name": "ecad_run_erc",
        "title": "Run ERC",
        "description": "Electrical rules check on the schematic; errors grouped.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": IDEMPOTENT,
    },
    {
        "name": "ecad_run_drc",
        "title": "Run DRC",
        "description": (
            "Design rules check on the board; errors grouped with positions. "
            "Optionally load a .dru rule file first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rules_file": {
                    "type": "string",
                    "description": "Path to a .dru design-rules file to load first",
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
    {
        "name": "ecad_review",
        "title": "Design Review",
        "description": (
            "Automated review of the whole design: missing values and MPNs, "
            "duplicate references, single-pin nets, parts outside the outline, "
            "overlapping footprints, decoupling distance, unrouted "
            "connections, power tracks too narrow for their current "
            "(IPC-2221), missing ground pour, and open DRC/ERC errors."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "power_currents": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "description": "Net name -> amps, e.g. {\"VMOT\": 13}",
                },
                "run_checks": {
                    "type": "boolean",
                    "default": True,
                    "description": "Run ERC and DRC first",
                },
                "decoupling_max_mm": {"type": "number", "default": 3.0},
            },
        },
    },
    # ── schematic edits ──────────────────────────────────────────────
    {
        "name": "ecad_add_sheet",
        "title": "Add Schematic Sheet",
        "description": "Add a schematic sheet and make it current.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
            },
        },
    },
    {
        "name": "ecad_add_part",
        "title": "Copy a Part",
        "description": (
            "Add a part to the schematic (and board) by copying a part "
            "already in the design with the same device, e.g. one more 100n "
            "capacitor. For a device the design does not use yet, add it to "
            "the spec and run ecad_build_design."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["name", "like", "x", "y"],
            "properties": {
                "name": {"type": "string", "description": "New reference, e.g. C12"},
                "like": {"type": "string", "description": "Existing part to copy"},
                "value": {"type": "string"},
                "x": _XY,
                "y": _XY,
                "sheet": {"type": "integer", "minimum": 1, "default": 1},
                "gate": {"type": "string"},
                "attributes": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
    },
    {
        "name": "ecad_set_part",
        "title": "Set Part Value or Attributes",
        "description": "Change a part's value and/or attributes.",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "string"},
                "attributes": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
    {
        "name": "ecad_connect",
        "title": "Connect Pins",
        "description": (
            "Connect pins to a named net in the schematic. Draws a short "
            "labelled stub from each pin; stubs with the same net name are "
            "the same net, so the schematic stays tidy. Pins are 'PART.PIN' "
            "using pin names, e.g. ['U1.VDD', 'C3.1']."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["net", "pins"],
            "properties": {
                "net": {"type": "string"},
                "pins": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string"},
                },
                "stub_length": {"type": "number", "default": 2.54},
            },
        },
    },
    # ── board edits ──────────────────────────────────────────────────
    {
        "name": "ecad_set_outline",
        "title": "Set Board Outline",
        "description": (
            "Draw the board outline on layer 20 (Dimension): a rectangle with "
            "optional rounded corners, or a polygon. Replaces any existing "
            "outline when replace is true."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "width": {"type": "number", "description": "mm"},
                "height": {"type": "number", "description": "mm"},
                "corner_radius": {"type": "number", "default": 0},
                "origin": {"type": "array", "items": {"type": "number"},
                           "minItems": 2, "maxItems": 2, "default": [0, 0]},
                "points": _POINTS,
                "replace": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "ecad_place",
        "title": "Place Components",
        "description": (
            "Move, rotate and flip board components. Each item: name, x, y, "
            "optional angle, side ('top'|'bottom'), lock. One call can place "
            "many parts."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["name", "x", "y"],
                        "properties": {
                            "name": {"type": "string"},
                            "x": _XY,
                            "y": _XY,
                            "angle": {"type": "number"},
                            "side": {"type": "string", "enum": ["top", "bottom"]},
                            "lock": {"type": "boolean"},
                        },
                    },
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
    {
        "name": "ecad_route",
        "title": "Route Track",
        "description": (
            "Draw a copper track for a signal through the given points on one "
            "layer. Add vias at layer changes with ecad_add_vias. Width in mm."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["signal", "points", "width"],
            "properties": {
                "signal": {"type": "string"},
                "points": _POINTS,
                "width": {"type": "number", "description": "Track width, mm"},
                "layer": {**_LAYER, "default": "top"},
            },
        },
    },
    {
        "name": "ecad_add_vias",
        "title": "Add Vias",
        "description": (
            "Add vias to a signal at given points, or fill a region with "
            "stitching vias at a pitch (keeps clear of pads and other vias)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["signal"],
            "properties": {
                "signal": {"type": "string"},
                "points": _POINTS,
                "stitch_region": {
                    **_POINTS,
                    "description": "Polygon to fill with stitching vias "
                                   "(or omit and set stitch_outline)",
                },
                "stitch_outline": {
                    "type": "boolean",
                    "default": False,
                    "description": "Stitch the whole board outline",
                },
                "pitch": {"type": "number", "default": 5.0},
                "edge_clearance": {"type": "number", "default": 1.0},
                "keepout": {"type": "number", "default": 1.0,
                            "description": "Clearance to pads/vias, mm"},
                "drill": {"type": "number", "default": 0.3},
                "diameter": {"type": "number", "default": 0.6},
            },
        },
    },
    {
        "name": "ecad_add_pour",
        "title": "Add Copper Pour",
        "description": (
            "Copper pour (polygon) for a signal on a layer, over given points "
            "or the board outline, then repour. Use rank to set priority."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["signal"],
            "properties": {
                "signal": {"type": "string"},
                "layer": {**_LAYER, "default": "top"},
                "points": _POINTS,
                "inset": {"type": "number", "default": 0.5,
                          "description": "When using the outline, mm inset"},
                "isolate": {"type": "number", "default": 0.3},
                "rank": {"type": "integer", "minimum": 1, "maximum": 6,
                         "default": 1},
                "thermals": {"type": "boolean", "default": True},
                "orphans": {"type": "boolean", "default": False},
                "width": {"type": "number", "default": 0.254},
            },
        },
    },
    {
        "name": "ecad_add_holes",
        "title": "Add Mounting Holes",
        "description": "Non-plated holes, e.g. M3 mounting holes (drill 3.2).",
        "inputSchema": {
            "type": "object",
            "required": ["holes"],
            "properties": {
                "holes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["x", "y", "drill"],
                        "properties": {"x": _XY, "y": _XY, "drill": _XY},
                    },
                },
            },
        },
    },
    {
        "name": "ecad_add_text",
        "title": "Add Text",
        "description": "Silkscreen or documentation text on the board.",
        "inputSchema": {
            "type": "object",
            "required": ["text", "x", "y"],
            "properties": {
                "text": {"type": "string"},
                "x": _XY,
                "y": _XY,
                "layer": {**_LAYER, "default": "tplace"},
                "size": {"type": "number", "default": 1.0},
                "ratio": {"type": "integer", "default": 15},
                "angle": {"type": "number", "default": 0},
            },
        },
    },
    {
        "name": "ecad_set_net_class",
        "title": "Set Net Class",
        "description": (
            "Define a net class (track width, clearance, via drill) and "
            "assign nets to it, e.g. a 'power' class for motor supply nets."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["number", "name"],
            "properties": {
                "number": {"type": "integer", "minimum": 0, "maximum": 7},
                "name": {"type": "string"},
                "width": {"type": "number", "description": "Min track width, mm"},
                "clearance": {"type": "number", "description": "mm"},
                "drill": {"type": "number", "description": "Min via drill, mm"},
                "nets": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "ecad_autoroute",
        "title": "Autoroute",
        "description": (
            "Run the autorouter on the board, or on listed signals only. "
            "Route power and sensitive signals by hand first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "signals": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "ecad_ripup",
        "title": "Rip Up Tracks",
        "description": (
            "Remove routed tracks (all, or listed signals) back to airwires."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "signals": {"type": "array", "items": {"type": "string"}},
                "polygons": {
                    "type": "boolean",
                    "default": False,
                    "description": "Unpour polygons instead of ripping tracks",
                },
            },
        },
        "annotations": DESTRUCTIVE,
    },
    {
        "name": "ecad_ratsnest",
        "title": "Ratsnest / Repour",
        "description": "Recalculate airwires and repour all copper polygons.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": IDEMPOTENT,
    },
    # ── raw access ───────────────────────────────────────────────────
    {
        "name": "ecad_command",
        "title": "Run EAGLE Commands",
        "description": (
            "Run EAGLE commands in the schematic or board editor (the full "
            "Fusion Electronics command language: ADD, NET, MOVE, WIRE, "
            "CHANGE, POLYGON, VIA, DELETE, GROUP, MITER, ...). Coordinates "
            "are mm. Runs as one script and reports what changed."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["commands"],
            "properties": {
                "commands": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": "One command per line or array item",
                },
                "editor": {"type": "string", "enum": ["schematic", "board"]},
            },
        },
        "annotations": DESTRUCTIVE,
    },
    {
        "name": "ecad_run_ulp",
        "title": "Run ULP",
        "description": (
            "Run an EAGLE User Language Program (.ulp) with arguments, e.g. "
            "teardrops.ulp, statistic-brd.ulp. Name a bundled ULP or give a "
            "full path."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["ulp"],
            "properties": {
                "ulp": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
                "editor": {"type": "string", "enum": ["schematic", "board"]},
            },
        },
    },
    # ── outputs ──────────────────────────────────────────────────────
    {
        "name": "ecad_export_bom",
        "title": "Export BOM",
        "description": (
            "Bill of materials grouped by value, package and MPN, as CSV. "
            "Writes the file when path is given; lists parts missing an MPN."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": _PATH,
                "group": {"type": "boolean", "default": True},
                "attribute_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["MPN", "MANUFACTURER"],
                },
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "ecad_export_pick_place",
        "title": "Export Pick-and-Place",
        "description": "Centroid file (SMD parts, top and bottom) as CSV.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": _PATH,
                "origin": {"type": "array", "items": {"type": "number"},
                           "minItems": 2, "maxItems": 2},
                "style": {"type": "string", "enum": ["jlcpcb", "generic"],
                          "default": "jlcpcb"},
                "include_tht": {"type": "boolean", "default": False},
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "ecad_export_netlist",
        "title": "Export Netlist",
        "description": "Netlist as 'NET: PART.PIN ...' text, optionally to a file.",
        "inputSchema": {"type": "object", "properties": {"path": _PATH}},
        "annotations": READ_ONLY,
    },
    {
        "name": "ecad_export_gerbers",
        "title": "Export Gerbers and Drill",
        "description": (
            "Run a CAM job to make Gerber, NC drill and assembly files into "
            "a folder (Fusion's Electron.mfgexport). Uses Fusion's bundled "
            "2- or 4-layer job when cam_job is not given. Fusion exports the "
            "last saved version, so an unsaved design is refused unless "
            "save_first is true."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["output_dir"],
            "properties": {
                "output_dir": _PATH,
                "cam_job": {"type": "string", "description": "Path to a .cam job"},
                "zip": {"type": "boolean", "default": True},
                "save_first": {"type": "boolean", "default": False},
            },
        },
        "annotations": IDEMPOTENT,
    },
    {
        "name": "ecad_export_odb",
        "title": "Export ODB++",
        "description": "ODB++ output through a CAM job (Electron.mfgodb).",
        "inputSchema": {
            "type": "object",
            "required": ["output_dir"],
            "properties": {
                "output_dir": _PATH,
                "cam_job": {"type": "string"},
                "save_first": {"type": "boolean", "default": False},
            },
        },
        "annotations": IDEMPOTENT,
    },
    {
        "name": "ecad_export_eagle",
        "title": "Export EAGLE Files",
        "description": (
            "Export the schematic (.sch), board (.brd) or used libraries "
            "(.lbr) as EAGLE XML: reviewable as text and diffable in git."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["kind", "path"],
            "properties": {
                "kind": {"type": "string", "enum": ["sch", "brd", "lbr"]},
                "path": _PATH,
            },
        },
        "annotations": IDEMPOTENT,
    },
    # ── engineering ──────────────────────────────────────────────────
    {
        "name": "ecad_calculate",
        "title": "Electronics Calculator",
        "description": (
            "Engineering calculators: trace_width (IPC-2221; current_a, "
            "temp_rise_c, copper_oz, layer, length_mm), via_current (drill_mm), "
            "divider (vin, vout, series, r_total_min, r_total_max, top), "
            "nearest_e (value, series), e_series (series, lo, hi), "
            "microstrip_impedance (width_mm, height_mm, er), "
            "microstrip_width_for (z0, height_mm, er), led_resistor "
            "(supply_v, led_vf, current_ma), rc_filter (two of r_ohm, c_f, "
            "fc_hz), resistor_power (r_ohm, v or i), parse_value (value)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["kind"],
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": [
                        "trace_width",
                        "via_current",
                        "divider",
                        "nearest_e",
                        "e_series",
                        "microstrip_impedance",
                        "microstrip_width_for",
                        "led_resistor",
                        "rc_filter",
                        "resistor_power",
                        "parse_value",
                    ],
                },
                "params": {"type": "object", "default": {}},
            },
        },
        "annotations": READ_ONLY,
    },
]


# ── mocks (--mode mock) ────────────────────────────────────────────────────

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


MOCKS: dict[str, Callable[[dict], dict]] = {
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

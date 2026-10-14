"""Surface and sheet-metal toolset: patch, stitch, thicken, ruled and trim
surfaces; flanges, bends, flat patterns and unfolds.
"""

from collections.abc import Callable

TOOLSET = "surface_sheetmetal"
SUMMARY = (
    "Surfaces (patch, stitch, thicken, ruled, trim) and sheet metal "
    "(flange, bend, flat pattern, unfold)"
)

TOOLS: list[dict] = [
    # ── surface operations ────────────────────────────────────────────────
    {
        "name": "patch_surface",
        "title": "Patch Surface",
        "description": ("Create a patch surface from boundary edges"),
        "inputSchema": {
            "type": "object",
            "required": ["sketch_name"],
            "properties": {
                "sketch_name": {
                    "type": "string",
                    "description": "Sketch with boundary curves",
                },
                "profile_index": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                },
                "continuity": {
                    "type": "string",
                    "enum": ["connected", "tangent", "curvature"],
                    "default": "connected",
                },
            },
        },
    },
    {
        "name": "stitch_surfaces",
        "title": "Stitch Surfaces",
        "description": ("Stitch surface bodies into a single body"),
        "inputSchema": {
            "type": "object",
            "required": ["body_names"],
            "properties": {
                "body_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                },
                "tolerance": {
                    "type": "number",
                    "default": 0.01,
                    "description": "Stitch tolerance (cm)",
                },
            },
        },
    },
    {
        "name": "thicken_surface",
        "title": "Thicken Surface",
        "description": "Thicken a surface body into a solid",
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "thickness"],
            "properties": {
                "body_name": {"type": "string"},
                "thickness": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Thickness (cm)",
                },
                "direction": {
                    "type": "string",
                    "enum": ["positive", "negative", "symmetric"],
                    "default": "symmetric",
                },
            },
        },
    },
    {
        "name": "ruled_surface",
        "title": "Ruled Surface",
        "description": ("Create a ruled surface from an edge or sketch curve"),
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "edge_index"],
            "properties": {
                "body_name": {"type": "string"},
                "edge_index": {
                    "type": "integer",
                    "minimum": 0,
                },
                "distance": {
                    "type": "number",
                    "default": 1.0,
                    "description": "Ruled surface distance (cm)",
                },
                "rule_type": {
                    "type": "string",
                    "enum": ["normal", "tangent"],
                    "default": "normal",
                },
            },
        },
    },
    {
        "name": "trim_surface",
        "title": "Trim Surface",
        "description": "Trim a surface body with another body",
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "tool_name"],
            "properties": {
                "body_name": {
                    "type": "string",
                    "description": "Surface body to trim",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Trimming tool body",
                },
            },
        },
    },
    # ── sheet metal ───────────────────────────────────────────────────────
    {
        "name": "create_flange",
        "title": "Create Flange",
        "description": ("Create a sheet metal flange on an edge"),
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "edge_index"],
            "properties": {
                "body_name": {"type": "string"},
                "edge_index": {
                    "type": "integer",
                    "minimum": 0,
                },
                "height": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Flange height (cm)",
                },
                "angle": {
                    "type": "number",
                    "default": 90,
                    "description": "Bend angle (degrees)",
                },
                "bend_radius": {
                    "type": "number",
                    "description": "Bend radius (cm)",
                },
            },
        },
    },
    {
        "name": "create_bend",
        "title": "Create Bend",
        "description": "Add a bend to a sheet metal body",
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "bend_line_sketch": {
                    "type": "string",
                    "description": "Sketch with bend line",
                },
                "angle": {
                    "type": "number",
                    "default": 90,
                    "description": "Bend angle (degrees)",
                },
                "bend_radius": {
                    "type": "number",
                    "description": "Override bend radius (cm)",
                },
            },
        },
    },
    {
        "name": "flat_pattern",
        "title": "Flat Pattern",
        "description": ("Create a flat pattern from a sheet metal body"),
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
            },
        },
    },
    {
        "name": "unfold",
        "title": "Unfold",
        "description": "Unfold specific bends in a sheet metal body",
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "bend_indices": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "description": ("Indices of bends to unfold (omit to unfold all)"),
                },
            },
        },
    },
]


# ── mocks (--mode mock) ────────────────────────────────────────────────────


def _patch_surface(p: dict) -> dict:
    return {
        "sketch_name": p.get("sketch_name", "Sketch1"),
        "body_name": "PatchSurface_mock",
        "continuity": p.get("continuity", "connected"),
    }


def _stitch_surfaces(p: dict) -> dict:
    return {
        "body_names": p.get("body_names", []),
        "result_body": "StitchedBody_mock",
        "tolerance": p.get("tolerance", 0.01),
    }


def _thicken_surface(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Surface1"),
        "thickness": p.get("thickness", 0.1),
        "result_body": "ThickenedBody_mock",
    }


def _ruled_surface(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Body1"),
        "edge_index": p.get("edge_index", 0),
        "distance": p.get("distance", 1.0),
        "result_body": "RuledSurface_mock",
    }


def _trim_surface(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Surface1"),
        "tool_name": p.get("tool_name", "Tool1"),
        "trimmed": True,
    }


def _create_flange(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "SheetBody1"),
        "edge_index": p.get("edge_index", 0),
        "height": p.get("height", 1.0),
        "angle": p.get("angle", 90),
    }


def _create_bend(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "SheetBody1"),
        "angle": p.get("angle", 90),
        "bend_radius": p.get("bend_radius", 0.1),
    }


def _flat_pattern(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "SheetBody1"),
        "flat_pattern_name": "FlatPattern_mock",
    }


def _unfold(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "SheetBody1"),
        "bends_unfolded": len(p.get("bend_indices", [0, 1])),
    }


MOCKS: dict[str, Callable[[dict], dict]] = {
    "patch_surface": _patch_surface,
    "stitch_surfaces": _stitch_surfaces,
    "thicken_surface": _thicken_surface,
    "ruled_surface": _ruled_surface,
    "trim_surface": _trim_surface,
    "create_flange": _create_flange,
    "create_bend": _create_bend,
    "flat_pattern": _flat_pattern,
    "unfold": _unfold,
}

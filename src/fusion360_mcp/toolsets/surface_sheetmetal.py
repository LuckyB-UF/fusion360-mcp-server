"""Surface and sheet-metal toolset: patch, stitch, thicken, ruled and trim
surfaces; flanges, bends, flat patterns and unfolds.
"""

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

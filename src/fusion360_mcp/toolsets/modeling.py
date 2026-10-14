"""Modeling toolset: the everyday sketch -> feature -> body loop.

Sketches, constraints, dimensions and curve edits; extrude, revolve,
fillet, chamfer, shell, mirror, holes and patterns; boolean, move and
rename.  All lengths are centimetres (Fusion's internal unit).
"""

from ._flags import IDEMPOTENT

TOOLSET = "modeling"
SUMMARY = (
    "Sketches, constraints, curve edits; extrude, revolve, fillet, "
    "chamfer, shell, mirror, holes, patterns; boolean, move, rename"
)

TOOLS: list[dict] = [
    # ── sketch ────────────────────────────────────────────────────────────
    {
        "name": "create_sketch",
        "title": "Create Sketch",
        "description": "Create a new sketch on xy/yz/xz plane, optionally offset",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plane": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "default": "xy",
                },
                "z_offset": {
                    "type": "number",
                    "description": "Offset distance from the plane (cm)",
                },
            },
        },
    },
    {
        "name": "draw_rectangle",
        "title": "Draw Rectangle",
        "description": "Draw a rectangle in the most recent sketch",
        "inputSchema": {
            "type": "object",
            "required": ["width", "height"],
            "properties": {
                "width": {"type": "number", "minimum": 0.001},
                "height": {"type": "number", "minimum": 0.001},
                "origin_x": {"type": "number", "default": 0},
                "origin_y": {"type": "number", "default": 0},
                "origin_z": {"type": "number", "default": 0},
            },
        },
    },
    {
        "name": "draw_circle",
        "title": "Draw Circle",
        "description": "Draw a circle in the most recent sketch",
        "inputSchema": {
            "type": "object",
            "required": ["radius"],
            "properties": {
                "radius": {"type": "number", "minimum": 0.001},
                "center_x": {"type": "number", "default": 0},
                "center_y": {"type": "number", "default": 0},
                "center_z": {"type": "number", "default": 0},
            },
        },
    },
    {
        "name": "draw_line",
        "title": "Draw Line",
        "description": "Draw a line in the most recent sketch",
        "inputSchema": {
            "type": "object",
            "required": ["start_x", "start_y", "end_x", "end_y"],
            "properties": {
                "start_x": {"type": "number"},
                "start_y": {"type": "number"},
                "start_z": {"type": "number", "default": 0},
                "end_x": {"type": "number"},
                "end_y": {"type": "number"},
                "end_z": {"type": "number", "default": 0},
            },
        },
    },
    {
        "name": "draw_arc",
        "title": "Draw Arc",
        "description": (
            "Draw an arc in the most recent sketch (center + start point + sweep angle)"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["center_x", "center_y", "start_x", "start_y", "sweep_angle"],
            "properties": {
                "center_x": {"type": "number"},
                "center_y": {"type": "number"},
                "center_z": {"type": "number", "default": 0},
                "start_x": {"type": "number"},
                "start_y": {"type": "number"},
                "start_z": {"type": "number", "default": 0},
                "sweep_angle": {
                    "type": "number",
                    "description": "Sweep angle in degrees (positive = CCW)",
                    "minimum": -360,
                    "maximum": 360,
                },
            },
        },
    },
    {
        "name": "draw_spline",
        "title": "Draw Spline",
        "description": (
            "Draw a spline in the most recent sketch. "
            "Use fit_points for a curve through points, or "
            "control_points for a control-polygon spline."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["spline_type", "points"],
            "properties": {
                "spline_type": {
                    "type": "string",
                    "enum": ["fit_points", "control_points"],
                },
                "points": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 3,
                    },
                    "minItems": 2,
                    "description": ("Array of [x,y] or [x,y,z] points"),
                },
                "degree": {
                    "type": "integer",
                    "enum": [3, 5],
                    "default": 3,
                    "description": ("Spline degree (only for control_points, 3 or 5)"),
                },
            },
        },
    },
    {
        "name": "create_polygon",
        "title": "Create Polygon",
        "description": "Draw a regular polygon in the most recent sketch",
        "inputSchema": {
            "type": "object",
            "required": ["sides", "radius"],
            "properties": {
                "sides": {"type": "integer", "minimum": 3, "maximum": 64},
                "radius": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Circumradius (cm)",
                },
                "center_x": {"type": "number", "default": 0},
                "center_y": {"type": "number", "default": 0},
                "center_z": {"type": "number", "default": 0},
            },
        },
    },
    # ── sketch constraints & dimensions ───────────────────────────────────
    {
        "name": "add_constraint",
        "title": "Add Sketch Constraint",
        "description": (
            "Add a geometric constraint in the active sketch. "
            "Entities are referenced by index within the sketch."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["constraint_type"],
            "properties": {
                "constraint_type": {
                    "type": "string",
                    "enum": [
                        "coincident",
                        "parallel",
                        "perpendicular",
                        "tangent",
                        "equal",
                        "fix",
                        "midpoint",
                        "concentric",
                        "horizontal",
                        "vertical",
                        "symmetry",
                        "collinear",
                        "smooth",
                    ],
                },
                "entity_one": {
                    "type": "integer",
                    "description": "Index of the first sketch entity",
                    "minimum": 0,
                },
                "entity_two": {
                    "type": "integer",
                    "description": (
                        "Index of the second sketch entity "
                        "(not needed for fix/horizontal/vertical)"
                    ),
                    "minimum": 0,
                },
                "symmetry_line": {
                    "type": "integer",
                    "description": (
                        "Index of the symmetry line (only for symmetry constraint)"
                    ),
                    "minimum": 0,
                },
                "sketch_name": {
                    "type": "string",
                    "description": "Sketch name (default: most recent)",
                },
            },
        },
    },
    {
        "name": "add_dimension",
        "title": "Add Sketch Dimension",
        "description": (
            "Add a driving dimension to constrain sketch geometry. "
            "Value is in cm for distances, degrees for angles."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["dimension_type", "value"],
            "properties": {
                "dimension_type": {
                    "type": "string",
                    "enum": [
                        "distance",
                        "horizontal",
                        "vertical",
                        "angular",
                        "radial",
                        "diameter",
                    ],
                },
                "value": {
                    "type": "number",
                    "description": "Dimension value (cm or degrees)",
                },
                "entity_one": {
                    "type": "integer",
                    "description": "Index of first entity (point or curve)",
                    "minimum": 0,
                },
                "entity_two": {
                    "type": "integer",
                    "description": (
                        "Index of second entity "
                        "(for distance/angular; not for radial/diameter)"
                    ),
                    "minimum": 0,
                },
                "sketch_name": {
                    "type": "string",
                    "description": "Sketch name (default: most recent)",
                },
            },
        },
    },
    # ── sketch curve operations ───────────────────────────────────────────
    {
        "name": "offset_curve",
        "title": "Offset Curve",
        "description": (
            "Offset connected sketch curves by a distance. "
            "Direction is determined by the direction_point."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["curve_index", "offset_distance"],
            "properties": {
                "curve_index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": ("Index of a curve in the connected loop"),
                },
                "offset_distance": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Offset distance (cm)",
                },
                "direction_x": {
                    "type": "number",
                    "default": 1,
                    "description": "X of direction point",
                },
                "direction_y": {
                    "type": "number",
                    "default": 0,
                    "description": "Y of direction point",
                },
                "sketch_name": {
                    "type": "string",
                    "description": ("Sketch name (default: most recent)"),
                },
            },
        },
    },
    {
        "name": "trim_curve",
        "title": "Trim Curve",
        "description": (
            "Trim a sketch curve at its intersections. "
            "The segment nearest to the given point is removed."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["curve_index", "point_x", "point_y"],
            "properties": {
                "curve_index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Index of the curve to trim",
                },
                "point_x": {
                    "type": "number",
                    "description": ("X near the segment to remove"),
                },
                "point_y": {
                    "type": "number",
                    "description": ("Y near the segment to remove"),
                },
                "sketch_name": {"type": "string"},
            },
        },
    },
    {
        "name": "extend_curve",
        "title": "Extend Curve",
        "description": (
            "Extend a sketch curve to the nearest intersection. "
            "The end nearest to the given point is extended."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["curve_index", "point_x", "point_y"],
            "properties": {
                "curve_index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Index of the curve to extend",
                },
                "point_x": {
                    "type": "number",
                    "description": "X near the end to extend",
                },
                "point_y": {
                    "type": "number",
                    "description": "Y near the end to extend",
                },
                "sketch_name": {"type": "string"},
            },
        },
    },
    {
        "name": "project_geometry",
        "title": "Project Geometry",
        "description": ("Project edges or bodies onto the active sketch plane"),
        "inputSchema": {
            "type": "object",
            "required": ["source_name"],
            "properties": {
                "source_name": {
                    "type": "string",
                    "description": ("Name of body or edge to project"),
                },
                "is_linked": {
                    "type": "boolean",
                    "default": True,
                    "description": ("True = parametrically linked to source geometry"),
                },
                "sketch_name": {
                    "type": "string",
                    "description": ("Target sketch (default: most recent)"),
                },
            },
        },
    },
    # ── features ──────────────────────────────────────────────────────────
    {
        "name": "extrude",
        "title": "Extrude",
        "description": "Extrude a sketch profile",
        "inputSchema": {
            "type": "object",
            "required": ["height"],
            "properties": {
                "height": {"type": "number"},
                "profile_index": {"type": "integer", "default": 0, "minimum": 0},
                "operation": {
                    "type": "string",
                    "enum": ["new_body", "join", "cut", "intersect"],
                    "default": "new_body",
                },
                "direction": {
                    "type": "string",
                    "enum": ["positive", "negative", "symmetric"],
                    "default": "positive",
                },
            },
        },
    },
    {
        "name": "revolve",
        "title": "Revolve",
        "description": "Revolve a sketch profile around an axis",
        "inputSchema": {
            "type": "object",
            "required": ["angle"],
            "properties": {
                "angle": {"type": "number", "minimum": 0.1, "maximum": 360},
                "profile_index": {"type": "integer", "default": 0},
                "axis_origin_x": {"type": "number", "default": 0},
                "axis_origin_y": {"type": "number", "default": 0},
                "axis_origin_z": {"type": "number", "default": 0},
                "axis_direction_x": {"type": "number", "default": 1},
                "axis_direction_y": {"type": "number", "default": 0},
                "axis_direction_z": {"type": "number", "default": 0},
                "operation": {
                    "type": "string",
                    "enum": ["new_body", "join", "cut", "intersect"],
                    "default": "new_body",
                },
            },
        },
    },
    {
        "name": "fillet",
        "title": "Fillet Edges",
        "description": "Round edges of a body",
        "inputSchema": {
            "type": "object",
            "required": ["radius"],
            "properties": {
                "radius": {"type": "number", "minimum": 0.001},
                "body_name": {"type": "string", "description": "Body name (preferred)"},
                "body_index": {"type": "integer", "default": 0},
                "edge_selection": {
                    "type": "string",
                    "enum": ["all", "top", "bottom", "vertical"],
                    "default": "all",
                },
            },
        },
    },
    {
        "name": "chamfer",
        "title": "Chamfer Edges",
        "description": "Chamfer edges of a body",
        "inputSchema": {
            "type": "object",
            "required": ["distance"],
            "properties": {
                "distance": {"type": "number", "minimum": 0.001},
                "body_name": {"type": "string"},
                "body_index": {"type": "integer", "default": 0},
                "edge_selection": {
                    "type": "string",
                    "enum": ["all", "top", "bottom", "vertical"],
                    "default": "all",
                },
            },
        },
    },
    {
        "name": "shell",
        "title": "Shell Body",
        "description": "Hollow out a body by removing a face",
        "inputSchema": {
            "type": "object",
            "required": ["thickness"],
            "properties": {
                "thickness": {"type": "number", "minimum": 0.001},
                "body_name": {"type": "string"},
                "body_index": {"type": "integer", "default": 0},
                "face_selection": {
                    "type": "string",
                    "enum": ["top", "bottom"],
                    "default": "top",
                },
            },
        },
    },
    {
        "name": "mirror",
        "title": "Mirror Body",
        "description": "Mirror a body across a construction plane",
        "inputSchema": {
            "type": "object",
            "required": ["mirror_plane"],
            "properties": {
                "mirror_plane": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                },
                "body_name": {"type": "string"},
                "body_index": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "create_hole",
        "title": "Create Hole",
        "description": "Create a hole feature on a body face",
        "inputSchema": {
            "type": "object",
            "required": ["diameter", "depth"],
            "properties": {
                "diameter": {"type": "number", "minimum": 0.001},
                "depth": {"type": "number", "minimum": 0.001},
                "body_name": {"type": "string"},
                "body_index": {"type": "integer", "default": 0},
                "face_selection": {
                    "type": "string",
                    "enum": ["top", "bottom"],
                    "default": "top",
                },
                "center_x": {"type": "number", "default": 0},
                "center_y": {"type": "number", "default": 0},
            },
        },
    },
    {
        "name": "rectangular_pattern",
        "title": "Rectangular Pattern",
        "description": "Pattern a body in rows and columns",
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "x_count": {"type": "integer", "minimum": 1, "default": 1},
                "x_spacing": {
                    "type": "number",
                    "default": 1.0,
                    "description": "Spacing between columns (cm)",
                },
                "y_count": {"type": "integer", "minimum": 1, "default": 1},
                "y_spacing": {
                    "type": "number",
                    "default": 1.0,
                    "description": "Spacing between rows (cm)",
                },
            },
        },
    },
    {
        "name": "circular_pattern",
        "title": "Circular Pattern",
        "description": "Pattern a body around an axis",
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "count"],
            "properties": {
                "body_name": {"type": "string"},
                "count": {"type": "integer", "minimum": 2},
                "axis": {
                    "type": "string",
                    "enum": ["x", "y", "z"],
                    "default": "z",
                },
                "total_angle": {
                    "type": "number",
                    "default": 360,
                    "minimum": 1,
                    "maximum": 360,
                    "description": "Total angle to distribute copies over (degrees)",
                },
            },
        },
    },
    # ── body operations ───────────────────────────────────────────────────
    {
        "name": "boolean_operation",
        "title": "Boolean Operation",
        "description": "Combine two named bodies (join/cut/intersect)",
        "inputSchema": {
            "type": "object",
            "required": ["target_body", "tool_body"],
            "properties": {
                "target_body": {"type": "string"},
                "tool_body": {"type": "string"},
                "operation": {
                    "type": "string",
                    "enum": ["join", "cut", "intersect"],
                    "default": "join",
                },
            },
        },
    },
    {
        "name": "move_body",
        "title": "Move Body",
        "description": "Translate a named body by (x, y, z)",
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "x": {"type": "number", "default": 0},
                "y": {"type": "number", "default": 0},
                "z": {"type": "number", "default": 0},
            },
        },
    },
    {
        "name": "rename_body",
        "title": "Rename Body",
        "description": "Rename a body (searches root and all components)",
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "new_name"],
            "properties": {
                "body_name": {
                    "type": "string",
                    "description": "Current body name",
                },
                "new_name": {
                    "type": "string",
                    "description": "New name for the body",
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
]

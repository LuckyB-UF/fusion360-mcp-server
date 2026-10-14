"""Advanced modeling toolset: the less common modeling tools.

Sweep and loft, threads, draft/split/offset/scale, suppress, direct
primitives, construction geometry, user parameters, appearance, the
per-format exports and ``delete_all``.  Kept out of the default listing
so a new agent starts with fewer tools.  Lengths are centimetres.
"""

from ._flags import DESTRUCTIVE, IDEMPOTENT, READ_ONLY

TOOLSET = "modeling_advanced"
SUMMARY = (
    "Sweep/loft, threads, draft/split/offset/scale, suppress, primitives, "
    "construction geometry, parameters, appearance, per-format exports, "
    "delete_all"
)

TOOLS: list[dict] = [
    # ── sweep / loft ──────────────────────────────────────────────────────
    {
        "name": "sweep",
        "title": "Sweep",
        "description": "Sweep a sketch profile along a path (sketch curve)",
        "inputSchema": {
            "type": "object",
            "required": ["profile_index", "path_sketch_name"],
            "properties": {
                "profile_index": {"type": "integer", "default": 0, "minimum": 0},
                "path_sketch_name": {
                    "type": "string",
                    "description": "Name of the sketch containing the sweep path",
                },
                "path_curve_index": {"type": "integer", "default": 0, "minimum": 0},
                "operation": {
                    "type": "string",
                    "enum": ["new_body", "join", "cut", "intersect"],
                    "default": "new_body",
                },
            },
        },
    },
    {
        "name": "loft",
        "title": "Loft",
        "description": "Loft between two or more sketch profiles",
        "inputSchema": {
            "type": "object",
            "required": ["profile_sketch_names"],
            "properties": {
                "profile_sketch_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "description": (
                        "Ordered list of sketch names whose "
                        "first profile will be lofted"
                    ),
                },
                "operation": {
                    "type": "string",
                    "enum": ["new_body", "join", "cut", "intersect"],
                    "default": "new_body",
                },
            },
        },
    },
    # ── advanced features ─────────────────────────────────────────────────
    {
        "name": "create_thread",
        "title": "Create Thread",
        "description": ("Add threads to a cylindrical face (cosmetic or modeled)"),
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "face_index"],
            "properties": {
                "body_name": {"type": "string"},
                "face_index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": ("Index of the cylindrical face"),
                },
                "is_internal": {
                    "type": "boolean",
                    "default": False,
                    "description": "True for internal (nut) threads",
                },
                "thread_type": {
                    "type": "string",
                    "default": "ISO Metric profile",
                    "description": (
                        "Thread standard "
                        "(e.g. 'ISO Metric profile', 'ANSI Unified Screw Threads')"
                    ),
                },
                "thread_designation": {
                    "type": "string",
                    "default": "M10x1.5",
                    "description": ("Size designation (e.g. 'M10x1.5')"),
                },
                "thread_class": {
                    "type": "string",
                    "default": "6g",
                    "description": "Thread class (e.g. '6g', '6H')",
                },
                "is_modeled": {
                    "type": "boolean",
                    "default": False,
                    "description": ("True = physical geometry, False = cosmetic"),
                },
                "is_full_length": {
                    "type": "boolean",
                    "default": True,
                    "description": "Thread entire cylinder length",
                },
                "thread_length": {
                    "type": "number",
                    "description": (
                        "Thread length in cm (only if is_full_length=false)"
                    ),
                },
            },
        },
    },
    {
        "name": "draft_faces",
        "title": "Draft / Taper Faces",
        "description": (
            "Add a draft angle to faces of a body "
            "(for mold release / injection molding)"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "angle"],
            "properties": {
                "body_name": {"type": "string"},
                "angle": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 89,
                    "description": "Draft angle in degrees",
                },
                "face_selection": {
                    "type": "string",
                    "enum": ["all", "top", "bottom", "vertical"],
                    "default": "vertical",
                    "description": "Which faces to draft",
                },
                "pull_direction_plane": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "default": "xy",
                    "description": "Plane defining the pull direction",
                },
                "is_tangent_chain": {
                    "type": "boolean",
                    "default": True,
                    "description": ("Include tangent-connected faces"),
                },
            },
        },
    },
    {
        "name": "split_body",
        "title": "Split Body",
        "description": "Split a body using a plane or face",
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "splitting_plane": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "default": "xy",
                    "description": ("Plane to split with (or use splitting_body)"),
                },
                "splitting_body": {
                    "type": "string",
                    "description": (
                        "Name of a body/surface to use "
                        "as splitting tool (overrides plane)"
                    ),
                },
                "extend_tool": {
                    "type": "boolean",
                    "default": True,
                    "description": ("Extend tool to cut through entire body"),
                },
            },
        },
    },
    {
        "name": "split_face",
        "title": "Split Face",
        "description": "Split faces of a body using a plane",
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "face_indices": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "description": ("Indices of faces to split (default: all faces)"),
                },
                "splitting_plane": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "default": "xy",
                },
                "extend_tool": {
                    "type": "boolean",
                    "default": True,
                },
            },
        },
    },
    {
        "name": "offset_faces",
        "title": "Offset Faces",
        "description": ("Push/pull faces of a body by a distance"),
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "distance"],
            "properties": {
                "body_name": {"type": "string"},
                "distance": {
                    "type": "number",
                    "description": ("Offset distance in cm (positive = outward)"),
                },
                "face_selection": {
                    "type": "string",
                    "enum": ["all", "top", "bottom"],
                    "default": "top",
                    "description": "Which faces to offset",
                },
                "face_indices": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "description": ("Specific face indices (overrides face_selection)"),
                },
            },
        },
    },
    {
        "name": "scale_body",
        "title": "Scale Body",
        "description": "Scale a body uniformly or non-uniformly",
        "inputSchema": {
            "type": "object",
            "required": ["body_name", "scale"],
            "properties": {
                "body_name": {"type": "string"},
                "scale": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Uniform scale factor",
                },
                "scale_x": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": ("X scale (overrides uniform scale)"),
                },
                "scale_y": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Y scale",
                },
                "scale_z": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Z scale",
                },
                "anchor_x": {
                    "type": "number",
                    "default": 0,
                    "description": "Scale anchor point X",
                },
                "anchor_y": {
                    "type": "number",
                    "default": 0,
                    "description": "Scale anchor point Y",
                },
                "anchor_z": {
                    "type": "number",
                    "default": 0,
                    "description": "Scale anchor point Z",
                },
            },
        },
    },
    # ── timeline control ──────────────────────────────────────────────────
    {
        "name": "suppress_feature",
        "title": "Suppress Feature",
        "description": "Suppress (disable) a feature in the timeline",
        "inputSchema": {
            "type": "object",
            "required": ["feature_name"],
            "properties": {
                "feature_name": {"type": "string"},
            },
        },
    },
    {
        "name": "unsuppress_feature",
        "title": "Unsuppress Feature",
        "description": "Unsuppress (re-enable) a feature in the timeline",
        "inputSchema": {
            "type": "object",
            "required": ["feature_name"],
            "properties": {
                "feature_name": {"type": "string"},
            },
        },
    },
    # ── direct primitives ─────────────────────────────────────────────────
    {
        "name": "create_box",
        "title": "Create Box",
        "description": (
            "Create a box primitive (non-parametric via TemporaryBRepManager)"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["length", "width", "height"],
            "properties": {
                "length": {"type": "number", "minimum": 0.001},
                "width": {"type": "number", "minimum": 0.001},
                "height": {"type": "number", "minimum": 0.001},
                "center_x": {"type": "number", "default": 0},
                "center_y": {"type": "number", "default": 0},
                "center_z": {"type": "number", "default": 0},
            },
        },
    },
    {
        "name": "create_box_parametric",
        "title": "Create Parametric Box",
        "description": (
            "Create a history-based rectangular box via sketch rectangle + "
            "extrude (unlike create_box which uses TemporaryBRepManager). "
            "length/width/height accept a number (cm, Fusion internal unit) "
            "or a string expression referencing User Parameters "
            "(e.g. 'boxL', '56 mm', 'outer - 2 * wall_t'). "
            "Call create_parameter first to define named parameters."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["length", "width", "height"],
            "properties": {
                "length": {
                    "oneOf": [
                        {"type": "number", "minimum": 0.001},
                        {"type": "string"},
                    ],
                    "description": "Along sketch X: number (cm) or expression",
                },
                "width": {
                    "oneOf": [
                        {"type": "number", "minimum": 0.001},
                        {"type": "string"},
                    ],
                    "description": "Along sketch Y: number (cm) or expression",
                },
                "height": {
                    "oneOf": [
                        {"type": "number", "minimum": 0.001},
                        {"type": "string"},
                    ],
                    "description": "Extrude distance: number (cm) or expression",
                },
                "origin_x": {"type": "number", "default": 0},
                "origin_y": {"type": "number", "default": 0},
                "origin_z": {
                    "type": "number", "default": 0,
                    "description": "Z-offset of sketch plane (cm)",
                },
                "plane": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "default": "xy",
                },
                "component_name": {
                    "type": "string",
                    "description": "Target component (omit for root)",
                },
                "body_name": {
                    "type": "string",
                    "description": "Optional name for the resulting body",
                },
            },
        },
    },
    {
        "name": "create_cylinder",
        "title": "Create Cylinder",
        "description": (
            "Create a cylinder primitive (non-parametric via TemporaryBRepManager)"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["radius", "height"],
            "properties": {
                "radius": {"type": "number", "minimum": 0.001},
                "height": {"type": "number", "minimum": 0.001},
                "base_x": {"type": "number", "default": 0},
                "base_y": {"type": "number", "default": 0},
                "base_z": {"type": "number", "default": 0},
                "axis": {
                    "type": "string",
                    "enum": ["x", "y", "z"],
                    "default": "z",
                    "description": "Cylinder axis direction",
                },
            },
        },
    },
    {
        "name": "create_sphere",
        "title": "Create Sphere",
        "description": (
            "Create a sphere primitive (non-parametric via TemporaryBRepManager)"
        ),
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
        "name": "create_torus",
        "title": "Create Torus",
        "description": (
            "Create a torus primitive (non-parametric via TemporaryBRepManager)"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["major_radius", "minor_radius"],
            "properties": {
                "major_radius": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Distance from center to tube center",
                },
                "minor_radius": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Tube cross-section radius",
                },
                "center_x": {"type": "number", "default": 0},
                "center_y": {"type": "number", "default": 0},
                "center_z": {"type": "number", "default": 0},
                "axis": {
                    "type": "string",
                    "enum": ["x", "y", "z"],
                    "default": "z",
                },
            },
        },
    },
    # ── construction geometry ─────────────────────────────────────────────
    {
        "name": "create_construction_plane",
        "title": "Create Construction Plane",
        "description": "Create a construction plane for sketching",
        "inputSchema": {
            "type": "object",
            "required": ["method"],
            "properties": {
                "method": {
                    "type": "string",
                    "enum": [
                        "offset",
                        "angle",
                        "midplane",
                        "three_points",
                        "tangent",
                    ],
                },
                "plane": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "description": ("Reference plane (for offset/angle)"),
                },
                "offset": {
                    "type": "number",
                    "description": "Offset distance in cm (for offset)",
                },
                "angle": {
                    "type": "number",
                    "description": "Angle in degrees (for angle method)",
                },
                "edge_name": {
                    "type": "string",
                    "description": ("Edge or axis to rotate around (for angle method)"),
                },
                "plane_one": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "description": "First plane (for midplane)",
                },
                "plane_two": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "description": "Second plane (for midplane)",
                },
                "point_one": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "[x,y,z] first point",
                },
                "point_two": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "[x,y,z] second point",
                },
                "point_three": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "[x,y,z] third point",
                },
            },
        },
    },
    {
        "name": "create_construction_axis",
        "title": "Create Construction Axis",
        "description": "Create a construction axis",
        "inputSchema": {
            "type": "object",
            "required": ["method"],
            "properties": {
                "method": {
                    "type": "string",
                    "enum": [
                        "two_points",
                        "intersection",
                        "edge",
                        "perpendicular_at_point",
                    ],
                },
                "point_one": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "point_two": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "plane_one": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "description": ("First plane (for intersection)"),
                },
                "plane_two": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "description": ("Second plane (for intersection)"),
                },
                "body_name": {
                    "type": "string",
                    "description": "Body name (for edge method)",
                },
                "edge_index": {
                    "type": "integer",
                    "description": "Edge index on the body",
                    "minimum": 0,
                },
            },
        },
    },
    # ── parameters ────────────────────────────────────────────────────────
    {
        "name": "get_parameters",
        "title": "Get Parameters",
        "description": "List all user parameters in the design",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "create_parameter",
        "title": "Create Parameter",
        "description": "Create a new user parameter",
        "inputSchema": {
            "type": "object",
            "required": ["name", "value", "unit"],
            "properties": {
                "name": {"type": "string", "description": "Parameter name"},
                "value": {"type": "number", "description": "Numeric value"},
                "unit": {
                    "type": "string",
                    "description": "Unit expression (e.g. 'mm', 'cm', 'in', 'deg')",
                },
                "comment": {"type": "string", "description": "Optional comment"},
            },
        },
    },
    {
        "name": "set_parameter",
        "title": "Set Parameter",
        "description": "Update the value of an existing user parameter",
        "inputSchema": {
            "type": "object",
            "required": ["name", "value"],
            "properties": {
                "name": {"type": "string", "description": "Parameter name"},
                "value": {"type": "number", "description": "New numeric value"},
            },
        },
        "annotations": IDEMPOTENT,
    },
    {
        "name": "delete_parameter",
        "title": "Delete Parameter",
        "description": "Remove a user parameter",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "Parameter name"},
            },
        },
        "annotations": DESTRUCTIVE,
    },
    # ── appearance / material ─────────────────────────────────────────────
    {
        "name": "set_appearance",
        "title": "Set Appearance",
        "description": (
            "Assign a material appearance to a body, face, "
            "or component from the Fusion appearance library"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["target_name", "appearance_name"],
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "Name of body or component",
                },
                "appearance_name": {
                    "type": "string",
                    "description": (
                        "Library appearance name "
                        "(e.g. 'Steel - Satin', "
                        "'Aluminum - Anodized Red')"
                    ),
                },
                "target_type": {
                    "type": "string",
                    "enum": ["body", "component", "face"],
                    "default": "body",
                },
                "face_index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": ("Face index (if target_type=face)"),
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
    # ── per-format export ─────────────────────────────────────────────────
    {
        "name": "export_stl",
        "title": "Export STL",
        "description": "Export a named body as an STL file",
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "file_path": {
                    "type": "string",
                    "description": "Destination path (default: ~/Desktop/<name>.stl)",
                },
            },
        },
    },
    {
        "name": "export_step",
        "title": "Export STEP",
        "description": "Export a body or component as a STEP file",
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "file_path": {
                    "type": "string",
                    "description": "Destination path (default: ~/Desktop/<name>.step)",
                },
            },
        },
    },
    {
        "name": "export_f3d",
        "title": "Export F3D",
        "description": "Export the design as a native Fusion 360 archive (.f3d)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Destination path (default: ~/Desktop/<design_name>.f3d)"
                    ),
                },
            },
        },
    },
    {
        "name": "export_view_sheet",
        "title": "Export View Sheet",
        "description": (
            "Render canonical orthographic + isometric views as PNGs and "
            "emit a self-contained HTML sheet suitable for sharing with a "
            "mechanical engineer. Opens in any browser; Print -> Save as "
            "PDF for a static artifact. Restores the viewport camera "
            "after rendering."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "Heading shown on the sheet "
                        "(default: document name)."
                    ),
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Free-form notes rendered below the views. "
                        "Newlines preserved; HTML is escaped."
                    ),
                },
                "views": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "iso", "iso_ne", "iso_nw", "iso_sw",
                            "front", "back", "top", "bottom",
                            "right", "left",
                        ],
                    },
                    "description": (
                        "Ordered list of views to render "
                        "(default: iso, front, top, right)."
                    ),
                },
                "image_size": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": (
                        "[width, height] in pixels (default [1200, 900])."
                    ),
                },
                "output_dir": {
                    "type": "string",
                    "description": (
                        "Destination folder "
                        "(default: ~/Desktop/<doc>_views_<timestamp>)."
                    ),
                },
            },
        },
    },
    # ── scene reset ───────────────────────────────────────────────────────
    {
        "name": "delete_all",
        "title": "Delete All",
        "description": "Clear the design (delete all timeline items)",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": DESTRUCTIVE,
    },
]

"""Advanced modeling toolset: the less common modeling tools.

Sweep and loft, threads, draft/split/offset/scale, suppress, direct
primitives, construction geometry, appearance, the per-format exports and
``delete_all``.  Kept out of the default listing so a new agent starts with
fewer tools.  Lengths are centimetres.
"""

from collections.abc import Callable

from ._flags import DESTRUCTIVE, IDEMPOTENT

TOOLSET = "modeling_advanced"
SUMMARY = (
    "Sweep/loft, threads, draft/split/offset/scale, suppress, primitives, "
    "construction geometry, appearance, per-format exports, delete_all"
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


# ── mocks (--mode mock) ────────────────────────────────────────────────────


def _sweep(p: dict) -> dict:
    return {
        "body_name": "Body_mock_sweep",
        "path_sketch_name": p.get("path_sketch_name", "PathSketch"),
        "operation": p.get("operation", "new_body"),
    }


def _loft(p: dict) -> dict:
    return {
        "body_name": "Body_mock_loft",
        "profile_sketch_names": p.get("profile_sketch_names", []),
        "operation": p.get("operation", "new_body"),
    }


def _create_thread(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Body1"),
        "face_index": p.get("face_index", 0),
        "is_modeled": p.get("is_modeled", False),
        "thread_designation": p.get("thread_designation", "M10x1.5"),
    }


def _draft_faces(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Body1"),
        "angle": p.get("angle", 5),
        "face_count": 4,
    }


def _split_body(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Body1"),
        "result_bodies": ["Body1", "Body1_split"],
    }


def _split_face(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Body1"),
        "faces_split": 2,
    }


def _offset_faces(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Body1"),
        "distance": p.get("distance", 0.5),
    }


def _scale_body(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Body1"),
        "scale": p.get("scale", 1.0),
    }


def _suppress_feature(p: dict) -> dict:
    return {
        "feature_name": p.get("feature_name", "Feature1"),
        "suppressed": True,
    }


def _unsuppress_feature(p: dict) -> dict:
    return {
        "feature_name": p.get("feature_name", "Feature1"),
        "suppressed": False,
    }


def _create_box(p: dict) -> dict:
    return {
        "body_name": "Box_mock",
        "length": p.get("length", 1),
        "width": p.get("width", 1),
        "height": p.get("height", 1),
    }


def _create_box_parametric(p: dict) -> dict:
    return {
        "created": True,
        "body_name": p.get("body_name") or "BoxParametric_mock",
        "feature_name": "Extrude_mock",
        "sketch_name": "Sketch_mock",
        "length": p.get("length", 1),
        "width": p.get("width", 1),
        "height": p.get("height", 1),
        "origin": [
            p.get("origin_x", 0),
            p.get("origin_y", 0),
            p.get("origin_z", 0),
        ],
        "plane": p.get("plane", "xy"),
        "component": p.get("component_name") or "RootComponent",
    }


def _create_cylinder(p: dict) -> dict:
    return {
        "body_name": "Cylinder_mock",
        "radius": p.get("radius", 1),
        "height": p.get("height", 1),
    }


def _create_sphere(p: dict) -> dict:
    return {
        "body_name": "Sphere_mock",
        "radius": p.get("radius", 1),
    }


def _create_torus(p: dict) -> dict:
    return {
        "body_name": "Torus_mock",
        "major_radius": p.get("major_radius", 2),
        "minor_radius": p.get("minor_radius", 0.5),
    }


def _create_construction_plane(p: dict) -> dict:
    return {
        "plane_name": "ConstructionPlane_mock",
        "method": p.get("method", "offset"),
    }


def _create_construction_axis(p: dict) -> dict:
    return {
        "axis_name": "ConstructionAxis_mock",
        "method": p.get("method", "two_points"),
    }


def _set_appearance(p: dict) -> dict:
    return {
        "target_name": p.get("target_name", "Body1"),
        "appearance_name": p.get("appearance_name", "Steel - Satin"),
        "applied": True,
    }


def _export_stl(p: dict) -> dict:
    name = p.get("body_name", "Body1")
    path = p.get("file_path", f"~/Desktop/{name}.stl")
    return {"body_name": name, "file_path": path}


def _export_step(p: dict) -> dict:
    name = p.get("body_name", "Body1")
    path = p.get("file_path", f"~/Desktop/{name}.step")
    return {"body_name": name, "file_path": path}


def _export_f3d(p: dict) -> dict:
    path = p.get("file_path", "~/Desktop/MockDesign.f3d")
    return {"file_path": path}


def _export_view_sheet(p: dict) -> dict:
    views = p.get("views") or ["iso", "front", "top", "right"]
    size = p.get("image_size") or [1200, 900]
    out = p.get("output_dir", "~/Desktop/MockDesign_views_mock")
    title = p.get("title", "MockDesign")
    return {
        "html_path": f"{out}/view_sheet.html",
        "output_dir": out,
        "title": title,
        "image_size": list(size),
        "views": [{"view": v, "path": f"{out}/{v}.png"} for v in views],
    }


def _delete_all(_p: dict) -> dict:
    return {"deleted": True}


MOCKS: dict[str, Callable[[dict], dict]] = {
    "sweep": _sweep,
    "loft": _loft,
    "create_thread": _create_thread,
    "draft_faces": _draft_faces,
    "split_body": _split_body,
    "split_face": _split_face,
    "offset_faces": _offset_faces,
    "scale_body": _scale_body,
    "suppress_feature": _suppress_feature,
    "unsuppress_feature": _unsuppress_feature,
    "create_box": _create_box,
    "create_box_parametric": _create_box_parametric,
    "create_cylinder": _create_cylinder,
    "create_sphere": _create_sphere,
    "create_torus": _create_torus,
    "create_construction_plane": _create_construction_plane,
    "create_construction_axis": _create_construction_axis,
    "set_appearance": _set_appearance,
    "export_stl": _export_stl,
    "export_step": _export_step,
    "export_f3d": _export_f3d,
    "export_view_sheet": _export_view_sheet,
    "delete_all": _delete_all,
}

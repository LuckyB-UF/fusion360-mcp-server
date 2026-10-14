"""Core toolset: always on.

Health, scene queries, design type, undo, ``execute_code``, ``render_view``
and the unified ``export`` / ``import_mesh``.
"""

from ._flags import IDEMPOTENT, READ_ONLY

TOOLSET = "core"
SUMMARY = (
    "Always on: health, scene info, design type, undo, execute_code, "
    "render_view, export/import, fusion_toolsets"
)

TOOLS: list[dict] = [
    # ── health ────────────────────────────────────────────────────────────
    {
        "name": "ping",
        "title": "Ping",
        "description": (
            "Health check — returns immediately without touching Fusion API"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": READ_ONLY,
    },
    # ── scene / query ─────────────────────────────────────────────────────
    {
        "name": "get_scene_info",
        "title": "Get Scene Info",
        "description": "Get design name, bodies, sketches, features, camera info",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "get_object_info",
        "title": "Get Object Info",
        "description": "Get detailed info about a named body or sketch",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "Object name"},
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "list_components",
        "title": "List Components",
        "description": "List all components in the design",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": READ_ONLY,
    },
    # ── design type safety ────────────────────────────────────────────────
    {
        "name": "get_design_type",
        "title": "Get Design Type",
        "description": (
            "Check if the design is in parametric or direct mode. "
            "Use this to detect accidental mode switches."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "set_design_type",
        "title": "Set Design Type",
        "description": (
            "Switch design type between 'parametric' and 'direct'. "
            "Use 'parametric' to recover from accidental direct-mode "
            "switches (equivalent to Capture Design History in the UI)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["design_type"],
            "properties": {
                "design_type": {
                    "type": "string",
                    "enum": ["parametric", "direct"],
                    "description": "Target design type",
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
    # ── history ───────────────────────────────────────────────────────────
    {
        "name": "undo",
        "title": "Undo",
        "description": "Undo the last operation",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    # ── code execution ────────────────────────────────────────────────────
    {
        "name": "execute_code",
        "title": "Execute Code",
        "description": (
            "Run arbitrary Python in Fusion 360. "
            "The last expression's value is returned (REPL-style). "
            "Pre-defined names: app, ui, design, component, adsk, math."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {"type": "string"},
            },
        },
    },
    # ── perception ────────────────────────────────────────────────────────
    {
        "name": "render_view",
        "title": "Render Viewport",
        "description": (
            "Capture the active viewport as a PNG so you can visually verify "
            "the model. Pass a canonical view (iso/front/top/etc.) to "
            "reposition the camera first, or 'current' to keep it as is. "
            "Returns base64-encoded image bytes alongside metadata; the MCP "
            "server delivers it as an image content block."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view": {
                    "type": "string",
                    "enum": [
                        "current",
                        "iso",
                        "front",
                        "back",
                        "top",
                        "bottom",
                        "left",
                        "right",
                    ],
                    "default": "current",
                    "description": (
                        "Camera preset; 'current' preserves the existing view"
                    ),
                },
                "width": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 4096,
                    "default": 1024,
                },
                "height": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 4096,
                    "default": 768,
                },
                "fit": {
                    "type": "boolean",
                    "default": True,
                    "description": "Call Viewport.fit() before capture",
                },
            },
        },
        "annotations": READ_ONLY,
    },
    # ── import / export ───────────────────────────────────────────────────
    {
        "name": "export",
        "title": "Export (unified)",
        "description": (
            "Unified export wrapper — dispatches to export_stl / export_step / "
            "export_f3d based on format or file extension. "
            "Format is auto-detected from file_path extension if not specified. "
            "STL and STEP require body_name; F3D exports the whole design."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["stl", "step", "stp", "f3d"],
                    "description": (
                        "Output format. Inferred from file_path extension "
                        "if omitted."
                    ),
                },
                "body_name": {
                    "type": "string",
                    "description": "Body to export (required for stl/step)",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Destination path (default: ~/Desktop/<name>.<ext>)"
                    ),
                },
            },
        },
    },
    {
        "name": "import_mesh",
        "title": "Import Mesh",
        "description": (
            "Import a mesh file (STL, OBJ, or 3MF) as a mesh body. "
            "Returns the mesh name and bounding box. "
            "Use for reference geometry (e.g. exported SketchUp model)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["file_path"],
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to mesh file (.stl/.obj/.3mf)",
                },
                "component_name": {
                    "type": "string",
                    "description": (
                        "Target component name (omit for root component)"
                    ),
                },
                "units": {
                    "type": "string",
                    "enum": ["mm", "cm", "m", "in", "ft"],
                    "default": "mm",
                    "description": "Source mesh units (default: mm)",
                },
            },
        },
    },
]

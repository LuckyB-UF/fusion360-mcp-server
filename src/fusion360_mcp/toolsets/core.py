"""Core toolset: always on.

Health, scene queries, design type, undo, ``execute_code``, ``render_view``,
the unified ``export`` / ``import_mesh``, and the open-document tools
(``docs_list`` / ``docs_activate`` / ``docs_open``) every toolset uses to
switch between designs, drawings and electronics documents.
"""

from collections.abc import Callable

from ..hints import classify as _classify
from ._flags import IDEMPOTENT, READ_ONLY

TOOLSET = "core"
SUMMARY = (
    "Always on: health, scene info, design type, undo, execute_code, "
    "render_view, export/import, open documents, fusion_toolsets"
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
    # ── open documents ────────────────────────────────────────────────────
    {
        "name": "docs_list",
        "title": "List Open Documents",
        "description": (
            "List the open documents: name, kind (fusion, drawing, "
            "electronics or other), whether each is active and saved, and "
            "its cloud file id (null until saved and uploaded; uploading is "
            "true meanwhile). Works whatever kind of "
            "document is active. Use it before docs_activate, and to find "
            "the design id for drawing_create."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "docs_activate",
        "title": "Activate Document",
        "description": (
            "Make an open document the active one, by name. The name matches "
            "with or without Fusion's version suffix ('Bracket' finds "
            "'Bracket v3'). Design tools need a fusion document active, "
            "drawing tools a drawing, ecad tools an electronics document."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Document name, as docs_list shows it",
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
    {
        "name": "docs_open",
        "title": "Open Cloud Document",
        "description": (
            "Open a cloud file by its file id and make it the active "
            "document. Opening a large design can take a while."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["file_id"],
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": (
                        "Cloud file id (the file_id from docs_list or "
                        "drawing_create)"
                    ),
                },
            },
        },
    },
]


# ── mocks (--mode mock) ────────────────────────────────────────────────────

# 1x1 transparent PNG, enough to exercise the image-content code path.
_MOCK_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0l"
    "EQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII="
)


def _ping(_p: dict) -> dict:
    return {"status": "pong"}


def _get_scene_info(_p: dict) -> dict:
    return {
        "design_name": "MockDesign",
        "bodies": ["Body1"],
        "sketches": ["Sketch1"],
        "features": ["Extrude1"],
        "components": ["RootComponent"],
    }


def _get_object_info(p: dict) -> dict:
    name = p.get("name", "Unknown")
    return {
        "name": name,
        "type": "BRepBody",
        "faces": 6,
        "edges": 12,
        "vertices": 8,
        "bounding_box": {"min": [0, 0, 0], "max": [1, 1, 1]},
    }


def _list_components(_p: dict) -> dict:
    return {
        "components": [
            {"name": "RootComponent", "bodies": ["Body1"]},
            {"name": "SubComponent1", "bodies": []},
        ],
    }


def _get_design_type(_p: dict) -> dict:
    return {"design_type": "parametric", "design_type_id": 1}


def _set_design_type(p: dict) -> dict:
    dt = p.get("design_type", "parametric")
    return {"changed": True, "design_type": dt}


def _undo(_p: dict) -> dict:
    return {"undone": True, "design_type": 1}


def _execute_code(p: dict) -> dict:
    return {"executed": True, "code": p.get("code", ""), "result": "None", "output": ""}


def _render_view(p: dict) -> dict:
    return {
        "view": p.get("view", "current"),
        "width": int(p.get("width", 1024)),
        "height": int(p.get("height", 768)),
        "image_format": "png",
        "image_base64": _MOCK_PNG_B64,
        "bytes": len(_MOCK_PNG_B64),
    }


def _export(p: dict) -> dict:
    fmt = (p.get("format") or "").lower()
    path = p.get("file_path", "")
    if not fmt and path:
        fmt = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    name = p.get("body_name", "Body1")
    return {
        "exported": True,
        "format": fmt or "f3d",
        "body": name,
        "file_path": path or f"~/Desktop/{name}.{fmt or 'f3d'}",
    }


def _import_mesh(p: dict) -> dict:
    path = p.get("file_path", "/tmp/mesh.stl")
    units = p.get("units", "mm")
    component = p.get("component_name") or "RootComponent"
    return {
        "imported": True,
        "file_path": path,
        "mesh_name": "MeshBody_mock",
        "component": component,
        "units": units,
        "bounding_box": {
            "min": [0.0, 0.0, 0.0],
            "max": [10.0, 5.0, 2.0],
            "size": [10.0, 5.0, 2.0],
        },
    }


_MOCK_DOCS = [
    {
        "name": "MockDesign v1",
        "kind": "fusion",
        "active": True,
        "saved": True,
        "uploading": False,
        "file_id": "urn:adsk.wipprod:dm.lineage:mockdesign",
    },
    {
        "name": "MockDesign Drawing v1",
        "kind": "drawing",
        "active": False,
        "saved": True,
        "uploading": False,
        "file_id": "urn:adsk.wipprod:dm.lineage:mockdrawing",
    },
]


def _docs_list(_p: dict) -> dict:
    return {
        "fusion_version": "2.0.mock",
        "active": dict(_MOCK_DOCS[0]),
        "count": len(_MOCK_DOCS),
        "documents": [dict(d) for d in _MOCK_DOCS],
    }


def _docs_activate(p: dict) -> dict:
    name = p.get("name", "MockDesign")
    for doc in _MOCK_DOCS:
        if doc["name"] == name or doc["name"].startswith(name + " v"):
            return {**doc, "active": True}
    message = f"No open document named {name!r}"
    kind, hint_list = _classify(message)
    return {
        "ok": False,
        "error_kind": kind,
        "error_message": message,
        "hints": hint_list,
        "traceback": f"MockError: {message}",
    }


def _docs_open(p: dict) -> dict:
    file_id = p.get("file_id", "urn:adsk.wipprod:dm.lineage:mock")
    return {
        "name": "Opened v1",
        "kind": "fusion",
        "active": True,
        "saved": True,
        "uploading": False,
        "file_id": file_id,
    }


MOCKS: dict[str, Callable[[dict], dict]] = {
    "ping": _ping,
    "get_scene_info": _get_scene_info,
    "get_object_info": _get_object_info,
    "list_components": _list_components,
    "get_design_type": _get_design_type,
    "set_design_type": _set_design_type,
    "undo": _undo,
    "execute_code": _execute_code,
    "render_view": _render_view,
    "export": _export,
    "import_mesh": _import_mesh,
    "docs_list": _docs_list,
    "docs_activate": _docs_activate,
    "docs_open": _docs_open,
}

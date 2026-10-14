"""CAM toolset: manufacturing setups, operations, toolpaths and
post-processing.
"""

from collections.abc import Callable

from ..hints import classify as _classify
from ._flags import READ_ONLY

TOOLSET = "cam"
SUMMARY = "Manufacturing setups, operations, toolpaths, post-processing"

TOOLS: list[dict] = [
    # ── CAM / manufacturing ───────────────────────────────────────────────
    {
        "name": "cam_create_setup",
        "title": "Create CAM Setup",
        "description": (
            "Create a manufacturing setup for a body. "
            "Defines the stock, coordinate system, and "
            "operation type (milling/turning/cutting)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {
                    "type": "string",
                    "description": "Body to machine",
                },
                "name": {
                    "type": "string",
                    "description": "Setup name",
                },
                "operation_type": {
                    "type": "string",
                    "enum": ["milling", "turning", "cutting"],
                    "default": "milling",
                },
                "stock_mode": {
                    "type": "string",
                    "enum": [
                        "relative_box",
                        "fixed_box",
                        "from_body",
                    ],
                    "default": "relative_box",
                },
                "stock_offset_sides": {
                    "type": "number",
                    "default": 0,
                    "description": "Side offset (cm)",
                },
                "stock_offset_top": {
                    "type": "number",
                    "default": 0,
                    "description": "Top offset (cm)",
                },
                "stock_offset_bottom": {
                    "type": "number",
                    "default": 0,
                    "description": "Bottom offset (cm)",
                },
            },
        },
    },
    {
        "name": "cam_list_strategies",
        "title": "List Compatible CAM Strategies",
        "description": (
            "List the machining strategies a setup accepts, split into "
            "turning and milling. Call this before cam_create_operation "
            "instead of guessing a strategy name."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["setup_name"],
            "properties": {
                "setup_name": {
                    "type": "string",
                    "description": "Setup to query",
                },
            },
        },
    },
    {
        "name": "cam_create_operation",
        "title": "Create CAM Operation",
        "description": (
            "Add a machining operation to a setup. "
            "Strategy determines the toolpath type."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["setup_name", "strategy"],
            "properties": {
                "setup_name": {
                    "type": "string",
                    "description": "Name of the parent setup",
                },
                "strategy": {
                    "type": "string",
                    "description": (
                        "Machining strategy, under the name Fusion uses "
                        "internally. Milling: face, contour2d, pocket2d, "
                        "adaptive2d, adaptive, drill, bore, engrave, trace, "
                        "slot, parallel, scallop, steep_and_shallow, "
                        "horizontal, pencil, radial, spiral, ramp, morph, "
                        "swarf, deburr, thread, chamfer2d, profile2d, "
                        "pocket_clearing, contour3d. Turning: turning_face, "
                        "turning_profile, turning_profile_roughing, "
                        "turning_profile_finishing, turning_groove_roughing, "
                        "turning_groove_finishing, turning_single_groove, "
                        "turning_chamfer, turning_thread, turning_part, "
                        "turning_trace, turning_adaptive_roughing, bar_pull. "
                        "There is no fixed enum: the valid set comes from "
                        "Operations.compatibleStrategies and depends on the "
                        "setup, so call cam_list_strategies rather than "
                        "guessing."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Operation name",
                },
                "tool_number": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Tool number from library",
                },
                "tool_diameter": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": (
                        "Tool diameter (cm) — used if tool_number not specified"
                    ),
                },
                "stepdown": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": "Axial depth of cut (cm)",
                },
                "stepover": {
                    "type": "number",
                    "minimum": 0.001,
                    "description": ("Radial stepover (cm)"),
                },
                "feed_rate": {
                    "type": "number",
                    "description": "Feed rate (cm/min)",
                },
                "spindle_speed": {
                    "type": "number",
                    "description": "Spindle speed (RPM)",
                },
                "coolant": {
                    "type": "string",
                    "enum": [
                        "disabled",
                        "flood",
                        "mist",
                        "through_tool",
                    ],
                    "default": "flood",
                },
            },
        },
    },
    {
        "name": "cam_generate_toolpath",
        "title": "Generate Toolpath",
        "description": (
            "Generate toolpaths for a specific operation or all operations in a setup"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "setup_name": {
                    "type": "string",
                    "description": ("Setup name (generates all its operations)"),
                },
                "operation_name": {
                    "type": "string",
                    "description": ("Specific operation name (overrides setup_name)"),
                },
                "generate_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "Generate all toolpaths",
                },
            },
        },
    },
    {
        "name": "cam_post_process",
        "title": "Post Process",
        "description": ("Post-process toolpaths to generate NC code (G-code)"),
        "inputSchema": {
            "type": "object",
            "required": ["setup_name"],
            "properties": {
                "setup_name": {
                    "type": "string",
                    "description": "Setup to post-process",
                },
                "operation_name": {
                    "type": "string",
                    "description": ("Specific operation (omit to post all in setup)"),
                },
                "post_processor": {
                    "type": "string",
                    "default": "fanuc",
                    "description": (
                        "Post processor name "
                        "(e.g. 'fanuc', 'grbl', 'haas', "
                        "'linuxcnc', 'mach3')"
                    ),
                },
                "output_folder": {
                    "type": "string",
                    "description": ("Output directory (default: ~/Desktop)"),
                },
                "output_units": {
                    "type": "string",
                    "enum": ["mm", "in"],
                    "default": "mm",
                },
            },
        },
    },
    {
        "name": "cam_list_setups",
        "title": "List CAM Setups",
        "description": ("List all manufacturing setups in the document"),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "cam_list_operations",
        "title": "List CAM Operations",
        "description": ("List operations within a setup"),
        "inputSchema": {
            "type": "object",
            "required": ["setup_name"],
            "properties": {
                "setup_name": {
                    "type": "string",
                },
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "cam_get_operation_info",
        "title": "Get CAM Operation Info",
        "description": (
            "Get details about a specific operation "
            "(strategy, tool, parameters, toolpath status)"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["setup_name", "operation_name"],
            "properties": {
                "setup_name": {"type": "string"},
                "operation_name": {"type": "string"},
            },
        },
        "annotations": READ_ONLY,
    },
]


# ── mocks (--mode mock) ────────────────────────────────────────────────────


def _cam_create_setup(p: dict) -> dict:
    stock_mode = p.get("stock_mode", "relative_box")
    if stock_mode != "relative_box":
        message = (
            f"stock_mode '{stock_mode}' cannot be applied through this tool. "
            "'fixed_box' needs explicit stock dimensions and 'from_body' "
            "needs a stock body, and neither argument exists on this tool. "
            "Use 'relative_box' with the stock_offset_* arguments, or set "
            "the stock mode through execute_code."
        )
        kind, hint_list = _classify(message)
        return {
            "ok": False,
            "error_kind": kind,
            "error_message": message,
            "hints": hint_list,
            "traceback": f"MockError: {message}",
            "mode": "mock",
        }
    offsets = {
        "job_stockOffsetSides": p.get("stock_offset_sides", 0),
        "job_stockOffsetTop": p.get("stock_offset_top", 0),
        "job_stockOffsetBottom": p.get("stock_offset_bottom", 0),
    }
    applied = {
        "stock_mode": {"value": 1},
        "job_stockOffsetMode": {"expression": "'simple'", "value": "simple"},
    }
    for name, value in offsets.items():
        applied[name] = {"expression": f"{value} cm", "value": value}

    return {
        "setup_name": p.get("name", "Setup1"),
        "body_name": p.get("body_name", "Body1"),
        "operation_type": p.get("operation_type", "milling"),
        "stock_mode": stock_mode,
        "applied": applied,
        "failed": {},
    }


def _cam_list_strategies(p: dict) -> dict:
    """A representative slice of a real turning setup's compatible list.

    Names are Fusion's internal strategy names, read off a live turning setup,
    not the friendlier titles shown in the UI.
    """
    return {
        "setup": p.get("setup_name", "Setup1"),
        "turning": [
            {"name": "turning_face", "title": "Turning Face"},
            {
                "name": "turning_profile_roughing",
                "title": "Turning Profile Roughing",
            },
            {
                "name": "turning_profile_finishing",
                "title": "Turning Profile Finishing",
            },
            {
                "name": "turning_groove_roughing",
                "title": "Turning Groove Roughing",
            },
            {"name": "turning_thread", "title": "Turning Thread"},
            {"name": "turning_part", "title": "Turning Part"},
        ],
        "milling": [
            {"name": "face", "title": "Face"},
            {"name": "contour2d", "title": "2D Contour"},
            {"name": "pocket2d", "title": "2D Pocket"},
            {"name": "adaptive2d", "title": "2D Adaptive Clearing"},
            {"name": "drill", "title": "Drill"},
            {"name": "bore", "title": "Bore"},
        ],
        "count": 12,
    }


def _cam_create_operation(p: dict) -> dict:
    """Mirror the addon: report Fusion's read-back, not the request.

    Lengths are given in cm and stored in mm, so the read-back value is ten
    times the argument. The mock reproduces that so a caller testing against
    ``--mode mock`` sees the same shape and the same unit shift as Fusion.
    """
    applied = {}

    if p.get("tool_number") is not None:
        tool_source = f"document tool library, tool number {p['tool_number']}"
    elif p.get("tool_diameter"):
        tool_source = f"diameter {p['tool_diameter']} cm"
    else:
        tool_source = None

    if p.get("tool_number") is None and p.get("tool_diameter"):
        applied["tool_diameter"] = {
            "expression": f"{p['tool_diameter']} cm",
            "value": p["tool_diameter"],
        }
    if p.get("stepdown"):
        applied["maximumStepdown"] = {
            "expression": f"{p['stepdown']} cm",
            "value": p["stepdown"],
        }
    if p.get("stepover"):
        applied["stepover"] = {
            "expression": f"{p['stepover']} cm",
            "value": p["stepover"],
        }
    if p.get("feed_rate") is not None:
        applied["tool_feedCutting"] = {
            "expression": f"{p['feed_rate']} cm/min",
            "value": p["feed_rate"] * 10,
        }
    if p.get("spindle_speed") is not None:
        applied["tool_spindleSpeed"] = {
            "expression": f"{int(p['spindle_speed'])}.rpm",
            "value": float(int(p["spindle_speed"])),
        }
    coolant = p.get("coolant", "flood")
    if coolant:
        applied["tool_coolant"] = {"expression": f"'{coolant}'", "value": coolant}

    return {
        "setup_name": p.get("setup_name", "Setup1"),
        "operation_name": p.get("name", "Operation1"),
        "strategy": p.get("strategy", "2d_contour"),
        "tool_diameter": p.get("tool_diameter", 0.6),
        "tool": tool_source,
        "applied": applied,
        "failed": {},
    }


def _cam_generate_toolpath(p: dict) -> dict:
    """Mirror the addon: a completed future is not a successful toolpath.

    The mock reports the same per-operation status the addon reads back, so a
    caller can write a gate against ``failures`` and have it behave the same
    in mock mode and in Fusion.
    """
    name = p.get("operation_name") or "Operation1"
    if p.get("generate_all"):
        scope = "all"
    elif p.get("operation_name"):
        scope = "operation"
    else:
        scope = "setup"

    status = {
        "name": name,
        "has_toolpath": True,
        "is_toolpath_valid": True,
        "has_error": False,
        "error": "",
        "has_warning": False,
        "warning": "",
    }
    return {
        "scope": scope,
        "generation_completed": True,
        "operations_total": 1,
        "operations_completed": 1,
        "generated": True,
        "failures": [],
        "operations": [status],
    }


def _cam_post_process(p: dict) -> dict:
    setup = p.get("setup_name", "Setup1")
    post = p.get("post_processor", "fanuc")
    return {
        "setup_name": setup,
        "post_processor": post,
        "output_file": f"~/Desktop/{setup}.nc",
        "output_units": p.get("output_units", "mm"),
    }


def _cam_list_setups(_p: dict) -> dict:
    return {
        "setups": [
            {
                "name": "Setup1",
                "operation_type": "milling",
                "operation_count": 2,
            },
        ],
    }


def _cam_list_operations(p: dict) -> dict:
    return {
        "setup_name": p.get("setup_name", "Setup1"),
        "operations": [
            {
                "name": "Face1",
                "strategy": "face",
                "has_toolpath": True,
            },
            {
                "name": "2D Contour1",
                "strategy": "2d_contour",
                "has_toolpath": False,
            },
        ],
    }


def _cam_get_operation_info(p: dict) -> dict:
    return {
        "setup_name": p.get("setup_name", "Setup1"),
        "operation_name": p.get("operation_name", "Face1"),
        "strategy": "face",
        "tool_diameter": 0.6,
        "stepdown": 0.1,
        "feed_rate": 100.0,
        "spindle_speed": 10000,
        "has_toolpath": True,
        "toolpath_valid": True,
    }


MOCKS: dict[str, Callable[[dict], dict]] = {
    "cam_create_setup": _cam_create_setup,
    "cam_list_strategies": _cam_list_strategies,
    "cam_create_operation": _cam_create_operation,
    "cam_generate_toolpath": _cam_generate_toolpath,
    "cam_post_process": _cam_post_process,
    "cam_list_setups": _cam_list_setups,
    "cam_list_operations": _cam_list_operations,
    "cam_get_operation_info": _cam_get_operation_info,
}

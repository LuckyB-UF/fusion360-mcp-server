"""CAM toolset: manufacturing setups, operations, toolpaths and
post-processing.
"""

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

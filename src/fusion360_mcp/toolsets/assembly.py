"""Assembly toolset: components, joints and rigid groups.
"""

TOOLSET = "assembly"
SUMMARY = "Components, joints, as-built joints, rigid groups"

TOOLS: list[dict] = [
    # ── assembly ──────────────────────────────────────────────────────────
    {
        "name": "create_component",
        "title": "Create Component",
        "description": "Create a new component (sub-assembly) in the design",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "Component name"},
                "parent_name": {
                    "type": "string",
                    "description": "Parent component name (omit for root)",
                },
            },
        },
    },
    {
        "name": "add_joint",
        "title": "Add Joint",
        "description": "Add a joint between two components",
        "inputSchema": {
            "type": "object",
            "required": ["component_one", "component_two"],
            "properties": {
                "component_one": {"type": "string"},
                "component_two": {"type": "string"},
                "joint_type": {
                    "type": "string",
                    "enum": [
                        "rigid",
                        "revolute",
                        "slider",
                        "cylindrical",
                        "pin_slot",
                        "planar",
                        "ball",
                    ],
                    "default": "rigid",
                },
            },
        },
    },
    {
        "name": "create_as_built_joint",
        "title": "Create As-Built Joint",
        "description": (
            "Create a joint from components' current positions "
            "(easier than geometric joints)"
        ),
        "inputSchema": {
            "type": "object",
            "required": [
                "component_one",
                "component_two",
                "joint_type",
            ],
            "properties": {
                "component_one": {"type": "string"},
                "component_two": {"type": "string"},
                "joint_type": {
                    "type": "string",
                    "enum": [
                        "rigid",
                        "revolute",
                        "slider",
                        "cylindrical",
                        "pin_slot",
                        "planar",
                        "ball",
                    ],
                    "default": "rigid",
                },
            },
        },
    },
    {
        "name": "create_rigid_group",
        "title": "Create Rigid Group",
        "description": "Lock multiple components together",
        "inputSchema": {
            "type": "object",
            "required": ["component_names"],
            "properties": {
                "component_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "description": "Names of components to group",
                },
                "include_children": {
                    "type": "boolean",
                    "default": True,
                    "description": ("Include child sub-components"),
                },
            },
        },
    },
]

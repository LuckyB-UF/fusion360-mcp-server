"""Assembly toolset: components, joints and rigid groups.
"""

from collections.abc import Callable

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


# ── mocks (--mode mock) ────────────────────────────────────────────────────


def _create_component(p: dict) -> dict:
    return {
        "component_name": p.get("name", "Component1"),
        "parent": p.get("parent_name", "RootComponent"),
    }


def _add_joint(p: dict) -> dict:
    return {
        "component_one": p.get("component_one", "Comp1"),
        "component_two": p.get("component_two", "Comp2"),
        "joint_type": p.get("joint_type", "rigid"),
        "joint_name": "Joint_mock",
    }


def _create_as_built_joint(p: dict) -> dict:
    return {
        "component_one": p.get("component_one", "Comp1"),
        "component_two": p.get("component_two", "Comp2"),
        "joint_type": p.get("joint_type", "rigid"),
        "joint_name": "AsBuiltJoint_mock",
    }


def _create_rigid_group(p: dict) -> dict:
    return {
        "component_names": p.get("component_names", []),
        "rigid_group_name": "RigidGroup_mock",
    }


MOCKS: dict[str, Callable[[dict], dict]] = {
    "create_component": _create_component,
    "add_joint": _add_joint,
    "create_as_built_joint": _create_as_built_joint,
    "create_rigid_group": _create_rigid_group,
}

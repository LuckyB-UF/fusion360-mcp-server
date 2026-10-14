"""Inspection toolset: measurements, bounding boxes, physical properties,
section analysis and interference checks.  Lengths are centimetres.
"""

from ._flags import READ_ONLY

TOOLSET = "inspection"
SUMMARY = (
    "Measure distance/angle, bounding box, physical properties, "
    "section analysis, interference"
)

TOOLS: list[dict] = [
    # ── inspection / analysis ─────────────────────────────────────────────
    {
        "name": "get_bounding_box",
        "title": "Get Bounding Box",
        "description": (
            "Axis-aligned bounding box for a body or component by name. "
            "Returns min, max, size, and center in cm (Fusion internal units). "
            "For components, unions bounding boxes of all contained bodies. "
            "Useful for measuring imported reference geometry."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Body or component name",
                },
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "measure_distance",
        "title": "Measure Distance",
        "description": ("Measure minimum distance between two entities"),
        "inputSchema": {
            "type": "object",
            "required": ["entity_one", "entity_two"],
            "properties": {
                "entity_one": {
                    "type": "string",
                    "description": (
                        "First entity name (body, sketch, or point 'x,y,z')"
                    ),
                },
                "entity_two": {
                    "type": "string",
                    "description": "Second entity name or point",
                },
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "measure_angle",
        "title": "Measure Angle",
        "description": "Measure angle between two entities",
        "inputSchema": {
            "type": "object",
            "required": ["entity_one", "entity_two"],
            "properties": {
                "entity_one": {
                    "type": "string",
                    "description": "First entity name (face, edge)",
                },
                "entity_two": {
                    "type": "string",
                    "description": "Second entity name",
                },
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "get_physical_properties",
        "title": "Get Physical Properties",
        "description": (
            "Get mass, volume, surface area, center of mass, and density of a body"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["body_name"],
            "properties": {
                "body_name": {"type": "string"},
                "accuracy": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "very_high"],
                    "default": "medium",
                },
            },
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "create_section_analysis",
        "title": "Create Section Analysis",
        "description": "Cut a section plane through the model",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plane": {
                    "type": "string",
                    "enum": ["xy", "yz", "xz"],
                    "default": "yz",
                },
                "offset": {
                    "type": "number",
                    "default": 0,
                    "description": "Offset from the plane (cm)",
                },
            },
        },
    },
    {
        "name": "check_interference",
        "title": "Check Interference",
        "description": ("Detect collisions between components/bodies"),
        "inputSchema": {
            "type": "object",
            "required": ["component_names"],
            "properties": {
                "component_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "description": ("Names of components to check"),
                },
                "include_coincident_faces": {
                    "type": "boolean",
                    "default": False,
                    "description": ("Count touching faces as interference"),
                },
            },
        },
        "annotations": READ_ONLY,
    },
]

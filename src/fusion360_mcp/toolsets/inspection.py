"""Inspection toolset: measurements, bounding boxes, physical properties,
section analysis and interference checks.  Lengths are centimetres.
"""

from collections.abc import Callable

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


# ── mocks (--mode mock) ────────────────────────────────────────────────────


def _get_bounding_box(p: dict) -> dict:
    name = p.get("name", "Unknown")
    return {
        "found": True,
        "type": "body",
        "name": name,
        "min": [0.0, 0.0, 0.0],
        "max": [50.0, 30.0, 15.0],
        "size": [50.0, 30.0, 15.0],
        "center": [25.0, 15.0, 7.5],
    }


def _measure_distance(p: dict) -> dict:
    return {
        "entity_one": p.get("entity_one", "Body1"),
        "entity_two": p.get("entity_two", "Body2"),
        "distance": 2.54,
        "point_one": [0, 0, 0],
        "point_two": [2.54, 0, 0],
    }


def _measure_angle(p: dict) -> dict:
    return {
        "entity_one": p.get("entity_one", "Face1"),
        "entity_two": p.get("entity_two", "Face2"),
        "angle_degrees": 90.0,
    }


def _get_physical_properties(p: dict) -> dict:
    return {
        "body_name": p.get("body_name", "Body1"),
        "mass": 0.785,
        "volume": 1.0,
        "area": 6.0,
        "density": 0.00785,
        "center_of_mass": [0.5, 0.5, 0.5],
    }


def _create_section_analysis(p: dict) -> dict:
    return {
        "plane": p.get("plane", "yz"),
        "offset": p.get("offset", 0),
        "analysis_name": "SectionAnalysis_mock",
    }


def _check_interference(p: dict) -> dict:
    return {
        "component_names": p.get("component_names", []),
        "interference_count": 0,
        "interferences": [],
    }


MOCKS: dict[str, Callable[[dict], dict]] = {
    "get_bounding_box": _get_bounding_box,
    "measure_distance": _measure_distance,
    "measure_angle": _measure_angle,
    "get_physical_properties": _get_physical_properties,
    "create_section_analysis": _create_section_analysis,
    "check_interference": _check_interference,
}

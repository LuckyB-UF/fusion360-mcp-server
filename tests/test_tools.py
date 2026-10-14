"""Tests for the tool registry."""

from fusion360_mcp.tools import SERVER_TOOLS, TOOLS, get_tool_by_name, get_tool_list
from fusion360_mcp.toolsets.electronics import TOOLS as ECAD_TOOLS


def test_all_tools_have_required_keys():
    for t in TOOLS:
        assert "name" in t, f"Tool missing 'name': {t}"
        assert "title" in t, f"Tool {t['name']} missing 'title'"
        assert "description" in t, f"Tool {t['name']} missing 'description'"
        assert "inputSchema" in t, f"Tool {t['name']} missing 'inputSchema'"


def test_all_schemas_are_objects():
    for t in TOOLS:
        schema = t["inputSchema"]
        assert schema.get("type") == "object", (
            f"Tool {t['name']} schema type is not 'object'"
        )


def test_required_fields_exist_in_properties():
    """Every field listed in 'required' must also appear in 'properties'."""
    for t in TOOLS:
        schema = t["inputSchema"]
        required = schema.get("required", [])
        props = schema.get("properties", {})
        for field in required:
            assert field in props, (
                f"Tool {t['name']}: required field '{field}' "
                f"not in properties {list(props)}"
            )


def test_no_duplicate_tool_names():
    names = [t["name"] for t in TOOLS]
    assert len(names) == len(set(names)), (
        f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"
    )


def test_get_tool_list_returns_mcp_types():
    tools = get_tool_list()
    assert len(tools) == len(TOOLS) + len(SERVER_TOOLS)
    for tool in tools:
        assert hasattr(tool, "name")
        assert hasattr(tool, "inputSchema")


def test_get_tool_by_name_found():
    assert get_tool_by_name("ping") is not None
    assert get_tool_by_name("extrude") is not None


def test_get_tool_by_name_missing():
    assert get_tool_by_name("nonexistent_tool") is None


def test_tool_count():
    """136 add-in commands; which ones is checked against the add-in's own
    dispatch tables in test_toolset_wiring.py."""
    assert len(TOOLS) == 136


def test_all_tools_have_annotations():
    """Every tool should have annotations after module load."""
    for t in TOOLS:
        ann = t.get("annotations")
        assert ann is not None, f"Tool {t['name']} missing annotations"
        for key in ("readOnlyHint", "destructiveHint", "idempotentHint"):
            assert key in ann, f"Tool {t['name']} missing annotation '{key}'"
            assert isinstance(ann[key], bool), f"Tool {t['name']}.{key} should be bool"


def test_property_types_are_valid():
    """Every property in every schema should have a valid JSON Schema type."""
    valid_types = {"string", "number", "integer", "boolean", "array", "object"}
    for t in TOOLS:
        props = t["inputSchema"].get("properties", {})
        for field, spec in props.items():
            if "type" in spec:
                assert spec["type"] in valid_types, (
                    f"Tool {t['name']}.{field}: invalid type '{spec['type']}'"
                )


def test_enum_fields_are_lists():
    """Every 'enum' in a property should be a non-empty list."""
    for t in TOOLS:
        props = t["inputSchema"].get("properties", {})
        for field, spec in props.items():
            if "enum" in spec:
                assert isinstance(spec["enum"], list), (
                    f"Tool {t['name']}.{field}: enum not a list"
                )
                assert len(spec["enum"]) > 0, f"Tool {t['name']}.{field}: enum is empty"


def test_minimum_less_than_maximum():
    """If both min and max are set, min should be < max."""
    for t in TOOLS:
        props = t["inputSchema"].get("properties", {})
        for field, spec in props.items():
            if "minimum" in spec and "maximum" in spec:
                assert spec["minimum"] < spec["maximum"], (
                    f"Tool {t['name']}.{field}: "
                    f"min ({spec['minimum']}) >= max ({spec['maximum']})"
                )


def test_descriptions_are_nonempty():
    """Every tool should have a non-empty description."""
    for t in TOOLS:
        assert len(t["description"].strip()) > 0, (
            f"Tool {t['name']} has empty description"
        )
        assert len(t["title"].strip()) > 0, f"Tool {t['name']} has empty title"


def test_tool_names_are_snake_case():
    """Tool names should be snake_case."""
    import re

    for t in TOOLS:
        assert re.match(r"^[a-z][a-z0-9_]*$", t["name"]), (
            f"Tool name '{t['name']}' is not snake_case"
        )


def test_get_tool_list_annotations_propagated():
    """MCP Tool objects should carry annotations."""
    tools = get_tool_list()
    for tool in tools:
        assert tool.annotations is not None, f"MCP Tool {tool.name} missing annotations"


def test_get_tool_by_name_returns_correct_tool():
    """get_tool_by_name should return the exact matching tool."""
    for t in TOOLS:
        found = get_tool_by_name(t["name"])
        assert found is t, f"get_tool_by_name('{t['name']}') returned wrong object"


def test_get_tool_by_name_edge_cases():
    assert get_tool_by_name("") is None
    assert get_tool_by_name("PING") is None  # case sensitive
    assert get_tool_by_name("ping ") is None  # trailing space


def test_ecad_tools_are_prefixed_and_counted():
    names = [t["name"] for t in ECAD_TOOLS]
    assert all(n.startswith("ecad_") for n in names)
    assert len(names) == 38

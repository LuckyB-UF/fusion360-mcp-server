"""The toolset split must not change a single tool schema.

``fixtures/tool_schemas_baseline.json`` is the MCP tool list as the server
exported it before the tools moved into ``toolsets/`` (128 tools).  Each tool
must still export to exactly the same JSON - name, title, description,
inputSchema (key order included) and annotations.
"""

import json
from pathlib import Path

from fusion360_mcp.tools import SERVER_TOOLS, get_tool_list

SERVER_ONLY = {t["name"] for t in SERVER_TOOLS}

_BASELINE = Path(__file__).parent / "fixtures" / "tool_schemas_baseline.json"


def _baseline() -> dict:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))


def _current() -> dict:
    return {
        t.name: t.model_dump(mode="json", exclude_none=True)
        for t in get_tool_list()
        if t.name not in SERVER_ONLY
    }


def test_same_tool_names_as_baseline():
    assert set(_current()) == set(_baseline())


def test_every_schema_matches_baseline_exactly():
    baseline = _baseline()
    for name, tool in _current().items():
        assert json.dumps(tool) == json.dumps(baseline[name]), name

"""The add-in's ecad handlers, the tool list and the mocks must agree."""

from __future__ import annotations

import ast
from pathlib import Path

from fusion360_mcp.hints import classify
from fusion360_mcp.mock import _DISPATCH, mock_command
from fusion360_mcp.tools_ecad import ECAD_TOOLS

_ECAD = Path(__file__).resolve().parent.parent / "addon" / "server" / "ecad.py"


def _handler_commands() -> set[str]:
    tree = ast.parse(_ECAD.read_text())
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "commands":
            for node in ast.walk(fn):
                if isinstance(node, ast.Dict):
                    return {k.value for k in node.keys}
    raise AssertionError("EcadHandler.commands() not found")


def _handler_params() -> dict[str, set[str]]:
    """Method name -> accepted parameter names, from ecad.py."""
    tree = ast.parse(_ECAD.read_text())
    out = {}
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        if cls.name != "EcadHandler":
            continue
        for fn in cls.body:
            if isinstance(fn, ast.FunctionDef):
                out[fn.name] = {a.arg for a in fn.args.args[1:]}
    return out


def _command_to_method() -> dict[str, str]:
    tree = ast.parse(_ECAD.read_text())
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "commands":
            for node in ast.walk(fn):
                if isinstance(node, ast.Dict):
                    return {k.value: v.attr for k, v in zip(node.keys, node.values)}
    return {}


def test_addon_handlers_match_tool_list():
    tools = {t["name"] for t in ECAD_TOOLS}
    assert _handler_commands() == tools


def test_every_ecad_tool_has_a_mock():
    for t in ECAD_TOOLS:
        assert t["name"] in _DISPATCH
        r = mock_command(t["name"], {})
        assert r["ok"] is True and r["mode"] == "mock"


def test_schema_properties_are_accepted_by_handlers():
    """Every property a tool schema offers must be a handler argument."""
    params = _handler_params()
    mapping = _command_to_method()
    for t in ECAD_TOOLS:
        method = mapping[t["name"]]
        props = set(t["inputSchema"].get("properties", {}))
        unknown = props - params[method]
        assert not unknown, f"{t['name']}: handler lacks {unknown}"
        required = set(t["inputSchema"].get("required", []))
        assert required <= params[method]


def test_ecad_errors_are_classified():
    assert classify("No electronics design is open. Open one")[0] == (
        "NO_ELECTRONICS_DESIGN")
    assert classify("This electronics design has no PCB yet.")[0] == (
        "ECAD_UNAVAILABLE")
    assert classify("U1 has no pin VDD. Pins: 1, 2")[0] == "ECAD_NOT_FOUND"

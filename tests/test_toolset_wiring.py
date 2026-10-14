"""Per toolset: server schemas, add-in dispatch and mocks name the same tools.

The add-in cannot import this package, so its dispatch tables are read by
AST: ``CommandHandler.execute_command``'s ``_COMMANDS`` dict and
``EcadHandler.commands()`` (spliced in with ``**self.ecad.commands()``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fusion360_mcp.tools import SERVER_TOOLS, TOOLS
from fusion360_mcp.toolsets import DOMAINS

_ADDON = Path(__file__).resolve().parent.parent / "addon" / "server"


def _dict_keys_in(path: Path, func: str) -> set[str]:
    """Literal keys of the dict built inside *func* (``**spread`` skipped)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == func:
            for node in ast.walk(fn):
                if isinstance(node, ast.Dict) and len(node.keys) > 10:
                    return {k.value for k in node.keys if k is not None}
    raise AssertionError(f"dispatch dict in {func}() not found in {path.name}")


def _addon_commands() -> dict[str, set[str]]:
    return {
        "command_handler": _dict_keys_in(
            _ADDON / "command_handler.py", "execute_command"
        ),
        "ecad": _dict_keys_in(_ADDON / "ecad.py", "commands"),
    }


def test_addon_tables_do_not_overlap():
    tables = _addon_commands()
    assert not tables["command_handler"] & tables["ecad"]


def test_server_tools_equal_addon_commands():
    addon = set().union(*_addon_commands().values())
    server = {t["name"] for t in TOOLS}
    assert server - addon == set(), "schemas with no add-in handler"
    assert addon - server == set(), "add-in handlers with no schema"


def test_server_only_tools_are_not_add_in_commands():
    addon = set().union(*_addon_commands().values())
    for t in SERVER_TOOLS:
        assert t["name"] not in addon


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.TOOLSET)
def test_toolset_schemas_mocks_and_handlers_agree(domain):
    names = {t["name"] for t in domain.TOOLS}
    assert len(names) == len(domain.TOOLS), "duplicate tool in toolset"
    assert set(domain.MOCKS) == names, "mocks differ from schemas"
    tables = _addon_commands()
    table = tables["ecad"] if domain.TOOLSET == "electronics" else (
        tables["command_handler"]
    )
    assert names <= table, f"no add-in handler for {sorted(names - table)}"


def test_ecad_table_is_exactly_the_electronics_toolset():
    electronics = next(d for d in DOMAINS if d.TOOLSET == "electronics")
    assert _addon_commands()["ecad"] == {t["name"] for t in electronics.TOOLS}

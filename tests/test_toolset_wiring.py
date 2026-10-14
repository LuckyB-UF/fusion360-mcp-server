"""Per toolset: server schemas, add-in dispatch and mocks name the same tools.

The add-in cannot import this package, so its dispatch tables are read by
AST: ``CommandHandler.execute_command``'s ``_COMMANDS`` dict,
``EcadHandler.commands()`` and ``DrawingHandler.commands()`` (spliced in with
``**self.ecad.commands()`` and ``**self.drawing.commands()``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fusion360_mcp.tools import SERVER_TOOLS, TOOLS
from fusion360_mcp.toolsets import DOMAINS

_ADDON = Path(__file__).resolve().parent.parent / "addon" / "server"


def _dict_keys_in(path: Path, func: str, min_keys: int = 10) -> set[str]:
    """Literal keys of the dict built inside *func* (``**spread`` skipped).

    The first dict with more than *min_keys* entries is the dispatch table.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == func:
            for node in ast.walk(fn):
                if isinstance(node, ast.Dict) and len(node.keys) > min_keys:
                    return {k.value for k in node.keys if k is not None}
    raise AssertionError(f"dispatch dict in {func}() not found in {path.name}")


def _addon_commands() -> dict[str, set[str]]:
    return {
        "command_handler": _dict_keys_in(
            _ADDON / "command_handler.py", "execute_command"
        ),
        "ecad": _dict_keys_in(_ADDON / "ecad.py", "commands"),
        "drawing": _dict_keys_in(_ADDON / "drawing.py", "commands", min_keys=3),
    }


# Toolset -> the add-in table its handlers live in (default command_handler).
_TABLE_OF = {"electronics": "ecad", "drawing": "drawing"}


def test_addon_tables_do_not_overlap():
    tables = list(_addon_commands().items())
    for i, (name_a, a) in enumerate(tables):
        for name_b, b in tables[i + 1:]:
            assert not a & b, f"{name_a} and {name_b} share {sorted(a & b)}"


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
    table = tables[_TABLE_OF.get(domain.TOOLSET, "command_handler")]
    assert names <= table, f"no add-in handler for {sorted(names - table)}"


def test_ecad_table_is_exactly_the_electronics_toolset():
    electronics = next(d for d in DOMAINS if d.TOOLSET == "electronics")
    assert _addon_commands()["ecad"] == {t["name"] for t in electronics.TOOLS}


def test_drawing_table_is_exactly_the_drawing_toolset():
    drawing = next(d for d in DOMAINS if d.TOOLSET == "drawing")
    assert _addon_commands()["drawing"] == {t["name"] for t in drawing.TOOLS}


def test_command_handler_splices_in_the_drawing_table():
    source = (_ADDON / "command_handler.py").read_text(encoding="utf-8")
    assert "**self.drawing.commands()" in source

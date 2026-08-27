"""Drift guards: assert addon-side and package-side mirrors stay in sync.

The Fusion add-in is installed into Fusion's AddIns folder and cannot
import from this package, so a few tables are duplicated:

* ``addon/server/hints.py:_RULES``   ↔  ``src/fusion360_mcp/hints.py:_RULES``
* ``CommandHandler._MUTATION_COMMANDS``  ↔  ``mock.py:_MUTATION_MOCKS``

If they drift, agents see different error envelopes / delta payloads
depending on whether they're running against Fusion or mock mode.  These
tests fail loudly the moment a maintainer updates one side without the
other.
"""

from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module_by_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _extract_class_attr_set(path: Path, class_name: str, attr: str) -> set[str]:
    """Pull ``ClassName.attr`` (a set/frozenset literal) out of *path* via AST.

    Avoids importing the addon module, which depends on Fusion's ``adsk``
    runtime and isn't installable in unit-test environments.
    """
    tree = ast.parse(path.read_text())
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        if cls.name != class_name:
            continue
        for stmt in cls.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == attr for t in stmt.targets):
                continue
            value = stmt.value
            # frozenset({...})  →  unwrap the set literal arg
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "frozenset"
                and value.args
            ):
                return set(ast.literal_eval(value.args[0]))
            return set(ast.literal_eval(value))
    raise AssertionError(f"{class_name}.{attr} not found in {path}")


def test_hints_rules_in_sync():
    """addon and src copies of hints._RULES must be identical."""
    addon_hints = _load_module_by_path(
        REPO_ROOT / "addon" / "server" / "hints.py", "_addon_hints"
    )
    src_hints = _load_module_by_path(
        REPO_ROOT / "src" / "fusion360_mcp" / "hints.py", "_src_hints"
    )
    assert addon_hints._RULES == src_hints._RULES, (
        "addon/server/hints.py and src/fusion360_mcp/hints.py have drifted. "
        "Update both files in lockstep."
    )


def test_mutation_sets_in_sync():
    """Addon mutation set and mock mutation set must be identical."""
    from fusion360_mcp.mock import _MUTATION_MOCKS

    addon_set = _extract_class_attr_set(
        REPO_ROOT / "addon" / "server" / "command_handler.py",
        "CommandHandler",
        "_MUTATION_COMMANDS",
    )
    mock_set = set(_MUTATION_MOCKS)
    assert addon_set == mock_set, (
        f"_MUTATION_COMMANDS (addon) and _MUTATION_MOCKS (mock.py) have drifted.\n"
        f"  only in addon: {sorted(addon_set - mock_set)}\n"
        f"  only in mock:  {sorted(mock_set - addon_set)}"
    )


# ---------------------------------------------------------------------------
# Deployment drift: the add-in Fusion actually runs vs. this repo.
#
# install-addon.sh intends a symlink, but `ln -s` under Git Bash on Windows
# silently falls back to a COPY unless developer mode / MSYS winsymlinks is
# on.  When that happens, editing the repo changes nothing Fusion executes,
# and a patch looks applied while the old code is still running - which is
# exactly how a fix for a bridge lockout was reported as live while Fusion
# kept raising the bug it fixed.
# ---------------------------------------------------------------------------


def _deployed_addon_dir() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    target = (
        Path(appdata)
        / "Autodesk"
        / "Autodesk Fusion 360"
        / "API"
        / "AddIns"
        / "Fusion360MCP"
        / "server"
    )
    return target if target.is_dir() else None


@pytest.mark.parametrize("filename", ["command_handler.py", "hints.py", "event_bridge.py"])
def test_deployed_addon_matches_repo(filename):
    """The installed add-in must be byte-identical to this repo's addon/server."""
    deployed = _deployed_addon_dir()
    if deployed is None:
        pytest.skip("no Fusion add-in installed on this machine")

    repo_file = REPO_ROOT / "addon" / "server" / filename
    live_file = deployed / filename
    if not live_file.exists():
        pytest.skip(f"{filename} not present in the installed add-in")

    assert live_file.read_text(encoding="utf-8") == repo_file.read_text(
        encoding="utf-8"
    ), (
        f"{filename} differs between this repo and the add-in Fusion runs "
        f"({live_file}). Copy it across, then reload the add-in in Fusion "
        f"(Shift+S). Editing the repo alone changes nothing Fusion executes."
    )

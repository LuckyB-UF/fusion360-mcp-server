"""Guards for the failure modes that break an unattended automation run.

Each test here pins one behaviour that, when it regressed, cost a real run:

* A timed-out mutating command was resent twice more, so one
  ``createDrawing()`` call produced three cloud documents.
* The client and add-in timeouts were tied at the same value, so which one
  fired was a scheduling race.
* ``execute_code`` refused to run without a Design product, which made the
  one tool that could switch documents unusable exactly when a non-design
  document was active.
* ``itemByProductType`` raises "failed to find product", which no rule
  matched, so the agent got a bare traceback and no hint.
"""

from __future__ import annotations

import ast
import re
import socket
from pathlib import Path

import pytest

from fusion360_mcp import hints
from fusion360_mcp.connection import Fusion360Connection
from fusion360_mcp.tools import _IDEMPOTENT

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestRetryIsGatedOnIdempotency:
    """A command that may have side effects is never resent on timeout."""

    def test_non_idempotent_command_is_not_retried(self, monkeypatch):
        monkeypatch.setattr("fusion360_mcp.connection._RETRY_DELAY", 0.01)

        conn = Fusion360Connection(host="127.0.0.1", port=1)
        conn._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        attempts = []
        real_connect = conn.connect

        def counting_connect():
            attempts.append(1)
            return real_connect()

        monkeypatch.setattr(conn, "connect", counting_connect)

        with pytest.raises(ConnectionError):
            conn.send_command("execute_code", {"code": "1+1"}, retries=2)

        assert attempts == [], (
            "execute_code was reconnected and resent after a socket failure. "
            "A mutating command that already reached Fusion must never be repeated."
        )

    def test_non_idempotent_failure_names_the_command_and_warns(self, monkeypatch):
        monkeypatch.setattr("fusion360_mcp.connection._RETRY_DELAY", 0.01)

        conn = Fusion360Connection(host="127.0.0.1", port=1)
        conn._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        with pytest.raises(ConnectionError) as excinfo:
            conn.send_command("extrude", {}, retries=2)

        message = str(excinfo.value)
        assert "extrude" in message
        assert "get_scene_info" in message, (
            "the error must tell the caller how to check whether the command "
            "partially applied before they repeat it"
        )

    def test_idempotent_command_still_retries(self, monkeypatch):
        monkeypatch.setattr("fusion360_mcp.connection._RETRY_DELAY", 0.01)

        conn = Fusion360Connection(host="127.0.0.1", port=1)
        conn._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        attempts = []
        monkeypatch.setattr(conn, "connect", lambda: attempts.append(1) or False)

        with pytest.raises(ConnectionError):
            conn.send_command("ping", retries=2)

        assert attempts, "a read-only command should still be retried"

    def test_execute_code_is_never_classified_idempotent(self):
        assert "execute_code" not in _IDEMPOTENT, (
            "execute_code runs arbitrary code and can never be assumed safe to repeat"
        )


class TestTimeoutsAreNotTied:
    """The add-in's own timeout must win, so the caller gets its error message."""

    def test_client_timeout_exceeds_addon_bridge_timeout(self):
        from fusion360_mcp import connection

        addon_bridge = REPO_ROOT / "addon" / "server" / "event_bridge.py"
        tree = ast.parse(addon_bridge.read_text())

        server_timeout = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "submit":
                for default in node.args.defaults:
                    if isinstance(default, ast.Constant) and isinstance(
                        default.value, float
                    ):
                        server_timeout = default.value
        assert server_timeout is not None, "could not read EventBridge.submit timeout"

        assert connection._TIMEOUT > server_timeout, (
            f"client timeout {connection._TIMEOUT}s must exceed the add-in's "
            f"{server_timeout}s, otherwise which side times out first is a race"
        )


class TestMissingDesignProductIsClassified:
    """The real exception text, not the handler's unreachable fallback message."""

    def test_failed_to_find_product_is_classified(self):
        kind, hint_list = hints.classify("3 : failed to find product")
        assert kind == "NO_DESIGN_PRODUCT"
        assert hint_list, "a classified error must carry at least one hint"

    def test_hint_names_the_drawing_document_cause(self):
        _, hint_list = hints.classify("3 : failed to find product")
        joined = " ".join(hint_list).lower()
        assert "drawing" in joined, (
            "the usual cause is a .f2d drawing document being active; say so"
        )


class TestExecuteCodeSurvivesWithoutDesign:
    """The add-in's recovery path must not require the thing it recovers from.

    ``execute_code`` is the only tool that can call ``document.activate()``.
    While it resolved a Design product before running user code, an active
    drawing document locked the bridge until a human clicked a model tab.
    Read as source: the add-in imports ``adsk`` and cannot be imported here.
    """

    def _execute_code_source(self) -> str:
        path = REPO_ROOT / "addon" / "server" / "command_handler.py"
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "execute_code":
                return ast.get_source_segment(path.read_text(), node) or ""
        pytest.fail("execute_code not found in command_handler.py")

    def test_design_resolution_is_guarded(self):
        src = self._execute_code_source()
        first_call = re.search(r"design\s*=\s*self\._design\(\)", src)
        assert first_call, "execute_code no longer resolves a design at all"

        preamble = src[: first_call.start()]
        assert "try:" in preamble, (
            "self._design() must sit inside a try block so a document with no "
            "Design product cannot lock execute_code out"
        )

    def test_root_component_is_guarded(self):
        src = self._execute_code_source()
        for match in re.finditer(r"self\._root\(\)", src):
            line_start = src.rfind("\n", 0, match.start()) + 1
            line = src[line_start : match.end()]
            assert "try" in src[max(0, line_start - 200) : match.start()], (
                "self._root() must be guarded too — it calls _design() and "
                "raises the same way"
            )

    def test_app_and_ui_are_always_bound(self):
        src = self._execute_code_source()
        assert '"app": self.app' in src
        assert '"ui": self.ui' in src, (
            "app and ui must be available even with no design, so user code "
            "can inspect and switch documents"
        )

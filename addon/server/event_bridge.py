"""
EventBridge — dispatches work from socket threads to Fusion's main thread.

Uses adsk.core.CustomEvent + a thread-safe queue so all Fusion API calls
happen on the main thread.  A 200 ms backup timer fires the custom event
periodically in case fireCustomEvent from a daemon thread is unreliable.
"""

import queue
import threading
import time
import traceback

import adsk.core

from . import dialog_guard, get_logger

log = get_logger("bridge")

CUSTOM_EVENT_ID = "Fusion360MCP_BridgeEvent"
TIMER_INTERVAL_MS = 200  # backup polling interval
DEFAULT_TIMEOUT = 30.0

# Commands that legitimately run longer than DEFAULT_TIMEOUT.  The MCP
# client's own limits (src/fusion360_mcp/connection.py) must stay above
# these; tests/test_ecad_wiring.py checks that.
LONG_COMMANDS = {
    "ecad_build_design": 150.0,   # importSchAndBrd: 10-23 s measured
    "ecad_new_design": 60.0,
    "ecad_open_editor": 60.0,
    "ecad_export_gerbers": 120.0,
    "ecad_export_odb": 120.0,
    "docs_open": 60.0,            # downloads the file first
    "drawing_create": 120.0,      # createDrawing lays out every view
    "drawing_autodim": 60.0,
    "drawing_tidy": 60.0,
    "drawing_export": 120.0,
}

# A modal dialog freezes the main thread.  For electronics commands, look
# for one after this many seconds, and close any that appeared.
DIALOG_CHECK_AFTER = 4.0


def timeout_for(cmd_type: str) -> float:
    return LONG_COMMANDS.get(cmd_type, DEFAULT_TIMEOUT)


class WorkItem:
    """One unit of work submitted from a socket thread."""

    __slots__ = ("command", "result", "error", "done")

    def __init__(self, command: dict):
        self.command = command
        self.result = None
        self.error = None
        self.done = threading.Event()


class _MainThreadHandler(adsk.core.CustomEventHandler):
    """Attached to the CustomEvent; runs on Fusion's main thread."""

    def __init__(self, bridge: "EventBridge"):
        super().__init__()
        self._bridge = bridge

    def notify(self, args):          # called on main thread
        self._bridge.drain_queue()


class EventBridge:
    """
    Bridge between daemon socket threads and Fusion's main thread.

    Socket thread calls ``submit(command)`` which blocks (up to *timeout*
    seconds) until the main thread has executed the command and stored the
    result.
    """

    def __init__(self, app: adsk.core.Application, command_handler):
        self._app = app
        self._handler = command_handler
        self._queue: queue.Queue = queue.Queue()

        # Register a custom event on the main thread
        self._event = app.registerCustomEvent(CUSTOM_EVENT_ID)
        self._event_handler = _MainThreadHandler(self)
        self._event.add(self._event_handler)

        # Backup timer thread — fires the custom event every 200 ms
        self._timer_running = True
        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

        log.info("EventBridge initialised (custom event: %s)", CUSTOM_EVENT_ID)

    # ------------------------------------------------------------------
    # Called from socket (daemon) threads
    # ------------------------------------------------------------------

    def submit(self, command: dict, timeout: float | None = None) -> dict:
        """Queue *command* for main-thread execution; block until done."""
        cmd_type = command.get("type", "?")
        if timeout is None:
            timeout = timeout_for(cmd_type)

        # Fast-path: ping never touches Fusion API — answer immediately
        if cmd_type == "ping":
            log.debug("ping (fast path)")
            return {"status": "success", "result": {"pong": True}}

        guarded = cmd_type.startswith("ecad_")
        before = set()
        if guarded:
            try:
                before = dialog_guard.snapshot()
            except Exception as exc:
                log.debug("dialog snapshot failed: %s", exc)
                guarded = False

        log.debug("submit cmd=%s", cmd_type)
        item = WorkItem(command)
        self._queue.put(item)

        # Poke the main thread
        try:
            self._app.fireCustomEvent(CUSTOM_EVENT_ID)
        except Exception:
            pass  # timer will pick it up

        closed = []
        start = time.monotonic()
        while not item.done.wait(timeout=1.0):
            elapsed = time.monotonic() - start
            if guarded and elapsed >= DIALOG_CHECK_AFTER:
                try:
                    closed += dialog_guard.dismiss_dialogs(exclude=before)
                except Exception as exc:
                    log.error("dialog dismiss failed: %s", exc)
            if elapsed >= timeout:
                break

        if not item.done.is_set():
            log.warning("Command %s timed out after %ss", cmd_type, timeout)
            msg = f"Command timed out after {timeout}s"
            if closed:
                msg += (". Fusion opened a dialog that was closed: "
                        + "; ".join(f"{d['title'] or d['class']}" for d in closed))
            return {"status": "error", "message": msg}

        if item.error is not None:
            log.error("Command %s failed: %s", cmd_type, item.error)
            msg = item.error
            if closed:
                msg = ("Fusion opened a dialog during this command and it was "
                       "closed without applying: " + "; ".join(
                           d["title"] or d["class"] for d in closed)
                       + ".\n" + msg)
            return {"status": "error", "message": msg}

        log.debug("Command %s completed", cmd_type)
        result = item.result
        if closed and isinstance(result, dict) and isinstance(
                result.get("result"), dict):
            result["result"]["dialogs_closed"] = closed
        return result

    # ------------------------------------------------------------------
    # Called on Fusion's main thread (from CustomEventHandler.notify)
    # ------------------------------------------------------------------

    def drain_queue(self):
        """Execute every queued work item (main thread only)."""
        while True:
            try:
                item: WorkItem = self._queue.get_nowait()
            except queue.Empty:
                break

            cmd_type = item.command.get("type", "?")
            try:
                item.result = self._handler.execute_command(item.command)
            except Exception as exc:
                item.error = f"{exc}\n{traceback.format_exc()}"
                log.error("Main-thread exec of %s raised: %s", cmd_type, exc)
            finally:
                item.done.set()

    # ------------------------------------------------------------------
    # Backup timer
    # ------------------------------------------------------------------

    def _timer_loop(self):
        interval = TIMER_INTERVAL_MS / 1000.0
        while self._timer_running:
            time.sleep(interval)
            if not self._queue.empty():
                try:
                    self._app.fireCustomEvent(CUSTOM_EVENT_ID)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Hot reload
    # ------------------------------------------------------------------

    def reload_handler(self):
        """Reimport command_handler and replace the active handler instance."""
        import importlib

        from . import command_handler as ch_mod
        importlib.reload(ch_mod)
        self._handler = ch_mod.CommandHandler()
        # Reset lazy dispatch table so it picks up new commands
        self._handler.__class__._COMMANDS = None
        log.info("CommandHandler reloaded")

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def stop(self):
        self._timer_running = False
        try:
            self._event.remove(self._event_handler)
        except Exception:
            pass
        try:
            self._app.unregisterCustomEvent(CUSTOM_EVENT_ID)
        except Exception:
            pass
        log.info("EventBridge stopped")

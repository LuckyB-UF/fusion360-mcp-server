"""
Close modal dialogs that block Fusion's main thread.

Some Fusion Electronics commands open a modal window when they are driven
from code: plain ``DRC`` opens the Design Rules dialog, a ``NET`` that
touches another net asks whether to merge, ``mfgexport`` asks whether to
export the last saved version, and a failed ``ADD`` shows an internal assert.
While that window is open the main thread is stuck, so every command queued
by this add-in times out.

This module runs on a socket thread (never the main thread).  It lists the
visible top-level windows owned by this Fusion process, other than the main
window and its known palettes, and sends each one WM_CLOSE.  Qt treats that
as "reject": a message box takes its escape button (Cancel or No), and a
dialog closes without applying anything.  Plain Win32 through ctypes, so it
needs nothing beyond the Python that ships with Fusion.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

from . import get_logger

log = get_logger("dialogs")

_WM_CLOSE = 0x0010

# Fusion's own long-lived windows: never touch these.
_SKIP_TITLES = ("Autodesk Fusion", "BROWSER", "Fusion360")
_SKIP_PREFIXES = ("Msg:",)
_SKIP_CLASSES = ("ToolbarFramework",)


def _windows() -> list[dict]:
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    pid = os.getpid()
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        found.append({"hwnd": hwnd, "title": title.value, "class": cls.value})
        return True

    user32.EnumWindows(_cb, 0)
    return found


def _is_dialog(w: dict) -> bool:
    t, c = w["title"], w["class"]
    if any(s in t for s in _SKIP_TITLES) or t.startswith(_SKIP_PREFIXES):
        return False
    if any(c.startswith(s) for s in _SKIP_CLASSES):
        return False
    return True


def snapshot() -> set:
    """Window handles of the dialogs open right now (left alone later)."""
    return {w["hwnd"] for w in _windows() if _is_dialog(w)}


def find_dialogs(exclude: set = frozenset()) -> list[dict]:
    """Fusion windows other than the main one (title and window class)."""
    return [{"title": w["title"], "class": w["class"]}
            for w in _windows() if _is_dialog(w) and w["hwnd"] not in exclude]


def dismiss_dialogs(exclude: set = frozenset(), wait: float = 3.0) -> list[dict]:
    """Close every Fusion dialog not in *exclude* (reject), then wait."""
    out = []
    targets = [w for w in _windows() if _is_dialog(w) and w["hwnd"] not in exclude]
    if not targets:
        return out
    user32 = ctypes.windll.user32
    for w in targets:
        user32.PostMessageW(w["hwnd"], _WM_CLOSE, 0, 0)
        out.append({"title": w["title"], "class": w["class"],
                    "action": "closed"})
        log.warning("Closed Fusion dialog %r (%s)", w["title"], w["class"])
    deadline = time.monotonic() + wait
    hwnds = {w["hwnd"] for w in targets}
    while time.monotonic() < deadline:
        if not hwnds & snapshot():
            return out
        time.sleep(0.2)
    still = snapshot()
    for w, rec in zip(targets, out):
        if w["hwnd"] in still:
            rec["action"] = "still open"
    return out

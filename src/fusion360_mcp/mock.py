"""
Mock responses for every Fusion 360 MCP command.

Used when the server is started with ``--mode mock`` so the full
tool→response pipeline can be tested without a running Fusion instance.
Every response includes ``"mode": "mock"`` so callers know it's simulated.
The handlers live next to their schemas in ``toolsets/<toolset>.py``
(``MOCKS``); this module adds the shared envelope.

The envelope matches the real addon: success results carry ``ok: True``,
mutation results carry a ``deltas`` sub-dict, and an ``__mock_error__``
sentinel in params forces a classified error response for tests.
"""

from typing import Any

from .hints import classify as _classify
from .toolsets import DOMAINS

# Mutation commands that get a synthetic deltas payload in mock mode.
# Keep in sync with CommandHandler._MUTATION_COMMANDS in the addon.
_MUTATION_MOCKS: frozenset[str] = frozenset(
    {
        "extrude",
        "revolve",
        "sweep",
        "loft",
        "fillet",
        "chamfer",
        "shell",
        "mirror",
        "create_hole",
        "rectangular_pattern",
        "circular_pattern",
        "create_thread",
        "draft_faces",
        "split_body",
        "split_face",
        "offset_faces",
        "scale_body",
        "suppress_feature",
        "unsuppress_feature",
        "move_body",
        "boolean_operation",
        "create_box",
        "create_cylinder",
        "create_sphere",
        "create_torus",
        "thicken_surface",
        "patch_surface",
        "stitch_surfaces",
        "ruled_surface",
        "trim_surface",
        "create_flange",
        "create_bend",
        "flat_pattern",
        "unfold",
        "delete_all",
        "undo",
        "set_parameter",
        "execute_code",
    }
)

_MOCK_DELTAS = {
    "body_count_before": 0,
    "body_count_after": 1,
    "body_count_delta": 1,
    "mass_g_before": 0.0,
    "mass_g_after": 10.0,
    "mass_g_delta": 10.0,
    "bbox_before": None,
    "bbox_after": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
}


def mock_command(command_type: str, params: dict[str, Any] | None = None) -> dict:
    """Return a plausible mock response for *command_type*.

    If *params* contains ``__mock_error__`` (a string message), the response
    simulates an addon-side failure: ``ok: False`` plus a classified
    ``error_kind`` and contextual ``hints``.
    """
    params = params or {}

    forced = params.get("__mock_error__")
    if forced is not None:
        kind, hint_list = _classify(str(forced))
        return {
            "ok": False,
            "error_kind": kind,
            "error_message": str(forced),
            "hints": hint_list,
            "traceback": f"MockError: {forced}",
            "mode": "mock",
        }

    handler = _DISPATCH.get(command_type, _default_mock)
    result = handler(params)
    result.setdefault("ok", True)
    if command_type in _MUTATION_MOCKS and "deltas" not in result:
        result["deltas"] = dict(_MOCK_DELTAS)
    result["mode"] = "mock"
    return result


def _default_mock(p: dict) -> dict:
    return {"warning": "no mock handler for this command", "params_received": p}


# Command name -> mock handler; each toolset module owns its handlers.
_DISPATCH: dict[str, Any] = {}
for _domain in DOMAINS:
    _DISPATCH.update(_domain.MOCKS)

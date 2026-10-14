"""
Tool registry: every tool the server offers, grouped into toolsets.

Each toolset is one module under ``toolsets/`` that owns its schemas, with
the read-only / destructive / idempotent flags set inline.  This module
assembles them, expands the flags into full MCP annotations and indexes the
tools by name.  The ``inputSchema`` is JSON Schema that the MCP SDK
validates before forwarding arguments to the Fusion360MCP add-in.

``TOOLS`` are the add-in's commands.  ``SERVER_TOOLS`` (``fusion_toolsets``)
are answered by the server itself and never forwarded.
"""

from collections.abc import Collection

import mcp.types as types

from .toolsets import DOMAINS
from .toolsets._flags import IDEMPOTENT

# Toolset name -> one-line summary, in listing order.
TOOLSETS: dict[str, str] = {d.TOOLSET: d.SUMMARY for d in DOMAINS}
ALWAYS_ON = "core"
DEFAULT_TOOLSETS = ("core", "modeling", "inspection")

_ANNOTATION_KEYS = ("readOnlyHint", "destructiveHint", "idempotentHint")


def _annotations(flags: dict | None) -> dict:
    """Expand an inline flag dict into the full annotation triple."""
    flags = flags or {}
    unknown = set(flags) - set(_ANNOTATION_KEYS)
    if unknown:
        raise ValueError(f"unknown annotation flags: {sorted(unknown)}")
    return {key: bool(flags.get(key, False)) for key in _ANNOTATION_KEYS}


# Commands the add-in executes, in listing order.
TOOLS: list[dict] = []
# Tool name -> tool dict, and tool name -> toolset name.
_BY_NAME: dict[str, dict] = {}
TOOLSET_OF: dict[str, str] = {}

for _domain in DOMAINS:
    for _t in _domain.TOOLS:
        _name = _t["name"]
        if _name in _BY_NAME:
            raise ValueError(f"tool {_name!r} is defined twice")
        _t["annotations"] = _annotations(_t.get("annotations"))
        TOOLS.append(_t)
        _BY_NAME[_name] = _t
        TOOLSET_OF[_name] = _domain.TOOLSET

_OPTIONAL = [name for name in TOOLSETS if name != ALWAYS_ON]

SERVER_TOOLS: list[dict] = [
    {
        "name": "fusion_toolsets",
        "title": "Fusion Toolsets",
        "description": (
            "List the toolsets (groups of tools), their tool counts and which "
            "are enabled, or turn toolsets on/off. Only tools of enabled "
            "toolsets are listed; core is always on. Not listed by default: "
            "modeling_advanced (sweep/loft, threads, primitives, construction "
            "geometry, appearance, per-format exports, delete_all), assembly, "
            "surface_sheetmetal, cam, electronics, drawing (Fusion drawings: "
            "create, auto-dimension, tidy, export)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "enable": {
                    "type": "array",
                    "items": {"type": "string", "enum": [*_OPTIONAL, "all"]},
                    "description": "Toolsets to turn on ('all' for every one)",
                },
                "disable": {
                    "type": "array",
                    "items": {"type": "string", "enum": [*_OPTIONAL, "all"]},
                    "description": "Toolsets to turn off ('all' leaves core)",
                },
            },
        },
        "annotations": IDEMPOTENT,
    },
]

for _t in SERVER_TOOLS:
    _t["annotations"] = _annotations(_t["annotations"])
    _BY_NAME[_t["name"]] = _t
    TOOLSET_OF[_t["name"]] = ALWAYS_ON

# Name sets by side-effect profile (connection.py retries only _IDEMPOTENT).
_READ_ONLY = {t["name"] for t in TOOLS if t["annotations"]["readOnlyHint"]}
_DESTRUCTIVE = {t["name"] for t in TOOLS if t["annotations"]["destructiveHint"]}
_IDEMPOTENT = {t["name"] for t in TOOLS if t["annotations"]["idempotentHint"]}


def _to_mcp(t: dict) -> types.Tool:
    return types.Tool(
        name=t["name"],
        title=t["title"],
        description=t["description"],
        inputSchema=t["inputSchema"],
        annotations=types.ToolAnnotations(**t["annotations"]),
    )


def get_tool_list(toolsets: Collection[str] | None = None) -> list[types.Tool]:
    """MCP Tool objects for *toolsets* (every toolset when None)."""
    return [
        _to_mcp(t)
        for t in SERVER_TOOLS + TOOLS
        if toolsets is None or TOOLSET_OF[t["name"]] in toolsets
    ]


def get_tool_by_name(name: str) -> dict | None:
    return _BY_NAME.get(name)

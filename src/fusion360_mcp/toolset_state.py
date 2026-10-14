"""Which toolsets a server instance lists, and the ``fusion_toolsets`` tool.

Selected at start-up with ``--toolsets`` / ``FUSION_MCP_TOOLSETS`` and
changed at runtime through ``fusion_toolsets``.  ``core`` is always on.
"""

import json

import mcp.types as types

from .tools import (
    ALWAYS_ON,
    SERVER_TOOLS,
    TOOLS,
    TOOLSET_OF,
    TOOLSETS,
    get_tool_list,
)

_COUNTS = {
    name: sum(TOOLSET_OF[t["name"]] == name for t in SERVER_TOOLS + TOOLS)
    for name in TOOLSETS
}


def parse_toolsets(spec: str) -> set[str]:
    """Parse a comma list of toolset names (or ``all``); core is always added.

    Raises ``ValueError`` naming the valid toolsets on an unknown name.
    """
    names = {part.strip().lower() for part in spec.split(",") if part.strip()}
    if "all" in names:
        return set(TOOLSETS)
    unknown = names - set(TOOLSETS)
    if unknown:
        raise ValueError(
            f"unknown toolset(s): {', '.join(sorted(unknown))}. "
            f"Valid: {', '.join(TOOLSETS)}, all"
        )
    return names | {ALWAYS_ON}


class ToolsetState:
    """The enabled toolsets of one server instance."""

    def __init__(self, enabled: set[str]):
        self.enabled = set(enabled) | {ALWAYS_ON}

    def tools(self) -> list[types.Tool]:
        """The MCP tool list for the enabled toolsets."""
        return get_tool_list(self.enabled)

    def is_enabled(self, tool_name: str) -> bool:
        return TOOLSET_OF.get(tool_name) in self.enabled

    def disabled_message(self, tool_name: str) -> str:
        toolset = TOOLSET_OF[tool_name]
        args = json.dumps({"enable": [toolset]})
        return (
            f"**{tool_name}** is in the '{toolset}' toolset, which is not "
            f"enabled.\n  Call fusion_toolsets with {args} to turn it on, "
            f"then call {tool_name} again."
        )

    def apply(self, arguments: dict) -> tuple[str, bool]:
        """Run ``fusion_toolsets``: enable, then disable, then report.

        Returns the report text and whether the enabled set changed.
        """
        before = set(self.enabled)
        for name in arguments.get("enable") or []:
            self.enabled |= set(TOOLSETS) if name == "all" else {name}
        for name in arguments.get("disable") or []:
            self.enabled -= set(TOOLSETS) if name == "all" else {name}
        self.enabled = (self.enabled & set(TOOLSETS)) | {ALWAYS_ON}
        changed = self.enabled != before
        return self._report(before, changed), changed

    def _report(self, before: set[str], changed: bool) -> str:
        on = [name for name in TOOLSETS if name in self.enabled]
        listed = sum(_COUNTS[name] for name in on)
        lines = [
            "**fusion_toolsets** OK",
            f"  enabled: {', '.join(on)} ({listed} tools listed)",
        ]
        if changed:
            added = [n for n in TOOLSETS if n in self.enabled - before]
            removed = [n for n in TOOLSETS if n in before - self.enabled]
            delta = [f"+{n}" for n in added] + [f"-{n}" for n in removed]
            lines.append(f"  changed: {' '.join(delta)} (tool list updated)")
        lines.append("  toolsets:")
        for name, summary in TOOLSETS.items():
            mark = "on " if name in self.enabled else "off"
            lines.append(f"    [{mark}] {name} ({_COUNTS[name]}): {summary}")
        return "\n".join(lines)

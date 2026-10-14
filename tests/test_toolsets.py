"""Toolsets: membership, default listing size, runtime switching."""

import mcp.types as types
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from fusion360_mcp.server import build_server, initialization_options
from fusion360_mcp.tools import (
    DEFAULT_TOOLSETS,
    SERVER_TOOLS,
    TOOLS,
    TOOLSET_OF,
    TOOLSETS,
    get_tool_list,
)
from fusion360_mcp.toolset_state import ToolsetState, parse_toolsets
from fusion360_mcp.toolsets import DOMAINS


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _names(tools) -> set[str]:
    return {t.name for t in tools}


# ── membership ───────────────────────────────────────────────────────


def test_every_tool_has_exactly_one_toolset():
    seen: dict[str, str] = {}
    for domain in DOMAINS:
        assert domain.TOOLS, f"empty toolset {domain.TOOLSET}"
        for t in domain.TOOLS:
            assert t["name"] not in seen, (
                f"{t['name']} in {seen.get(t['name'])} and {domain.TOOLSET}"
            )
            seen[t["name"]] = domain.TOOLSET
    assert all(TOOLSET_OF[n] == s for n, s in seen.items())
    every = {t["name"] for t in TOOLS + SERVER_TOOLS}
    assert set(TOOLSET_OF) == every
    assert set(TOOLSET_OF.values()) == set(TOOLSETS)


def test_fusion_toolsets_is_core():
    assert TOOLSET_OF["fusion_toolsets"] == "core"


def test_electronics_toolset_is_the_ecad_tools():
    ecad = {n for n, s in TOOLSET_OF.items() if s == "electronics"}
    assert ecad == {t["name"] for t in TOOLS if t["name"].startswith("ecad_")}
    cam = {n for n, s in TOOLSET_OF.items() if s == "cam"}
    assert cam == {t["name"] for t in TOOLS if t["name"].startswith("cam_")}


# ── listing size ─────────────────────────────────────────────────────


def test_core_stays_small():
    core = get_tool_list({"core"})
    assert len(core) <= 15


def test_default_listing_is_core_modeling_inspection():
    assert DEFAULT_TOOLSETS == ("core", "modeling", "inspection")
    tools = ToolsetState(set(DEFAULT_TOOLSETS)).tools()
    assert {TOOLSET_OF[t.name] for t in tools} == set(DEFAULT_TOOLSETS)
    assert len(tools) <= 50


def test_all_lists_every_tool():
    tools = ToolsetState(parse_toolsets("all")).tools()
    assert len(tools) == 136 + 1
    assert _names(tools) == {t["name"] for t in TOOLS} | {"fusion_toolsets"}


# ── selection ────────────────────────────────────────────────────────


def test_parse_adds_core_and_ignores_case_and_spaces():
    assert parse_toolsets(" CAM , electronics") == {"core", "cam", "electronics"}
    assert parse_toolsets("") == {"core"}


def test_parse_rejects_unknown_toolsets():
    with pytest.raises(ValueError, match="nonesuch"):
        parse_toolsets("core,nonesuch")


def test_state_cannot_disable_core():
    state = ToolsetState({"core", "cam"})
    _, changed = state.apply({"disable": ["all"]})
    assert changed and state.enabled == {"core"}


def test_report_lists_every_toolset_with_counts():
    text, changed = ToolsetState(set(DEFAULT_TOOLSETS)).apply({})
    assert not changed
    for name in TOOLSETS:
        assert f"] {name} (" in text
    assert "[on ] modeling" in text and "[off] cam" in text


# ── through the MCP protocol ─────────────────────────────────────────


def test_capability_declares_tools_list_changed():
    opts = initialization_options(build_server("mock"))
    assert opts.capabilities.tools is not None
    assert opts.capabilities.tools.listChanged is True


def _session(app, notes: list):
    async def on_message(message):
        if isinstance(message, types.ServerNotification):
            notes.append(message.root)

    return create_connected_server_and_client_session(app, message_handler=on_message)


@pytest.mark.anyio
async def test_enabling_a_toolset_changes_the_list_and_notifies():
    notes: list = []
    app = build_server("mock", toolsets=set(DEFAULT_TOOLSETS))
    async with _session(app, notes) as client:
        before = _names((await client.list_tools()).tools)
        assert "cam_list_setups" not in before
        assert "fusion_toolsets" in before

        result = await client.call_tool("fusion_toolsets", {"enable": ["cam"]})
        assert not result.isError
        assert "+cam" in result.content[0].text

        after = _names((await client.list_tools()).tools)
        assert after - before == {
            n for n, s in TOOLSET_OF.items() if s == "cam"
        }
        assert any(isinstance(n, types.ToolListChangedNotification) for n in notes)

        # A call that changes nothing sends no further notification.
        count = len(notes)
        await client.call_tool("fusion_toolsets", {"enable": ["cam"]})
        await client.list_tools()
        assert len(notes) == count


@pytest.mark.anyio
async def test_disabled_toolset_call_says_how_to_enable_it():
    app = build_server("mock", toolsets={"core"})
    async with _session(app, []) as client:
        result = await client.call_tool("cam_list_setups", {})
        assert result.isError
        text = result.content[0].text
        assert "'cam' toolset" in text
        assert 'fusion_toolsets with {"enable": ["cam"]}' in text

        await client.call_tool("fusion_toolsets", {"enable": ["cam"]})
        result = await client.call_tool("cam_list_setups", {})
        assert not result.isError
        assert "cam_list_setups" in result.content[0].text


@pytest.mark.anyio
async def test_enabled_tool_still_forwards_in_mock_mode():
    app = build_server("mock")
    async with _session(app, []) as client:
        result = await client.call_tool("ping", {})
        assert not result.isError
        assert "pong" in result.content[0].text


def test_cli_rejects_unknown_toolset_from_flag_or_env():
    from click.testing import CliRunner

    from fusion360_mcp.server import main

    runner = CliRunner()
    result = runner.invoke(main, ["--mode", "mock", "--toolsets", "nonesuch"])
    assert result.exit_code == 2 and "nonesuch" in result.output
    result = runner.invoke(main, ["--mode", "mock"], env={"FUSION_MCP_TOOLSETS": "x"})
    assert result.exit_code == 2 and "unknown toolset" in result.output

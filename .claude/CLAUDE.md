# Fusion360 MCP Server

## What this is

An MCP server that bridges Claude Code to Autodesk Fusion 360 for CAD automation. Two components:

1. **This repo** — Python MCP server (stdio transport, 136 Fusion tools in 9 toolsets, plus `fusion_toolsets`). Claude talks to this.
2. **Fusion360MCP add-in** — installed in Fusion's AddIns folder. Listens on `localhost:9876`.

The MCP server receives tool calls from Claude, forwards them as JSON over TCP to the add-in, and returns results.

## Architecture

```
Claude Code ←(stdio MCP)→ This Server ←(TCP :9876)→ Fusion360MCP Add-in ←(CustomEvent)→ Fusion Main Thread
```

## Development

```bash
uv sync --dev      # install deps
uv run pytest -v   # run tests (501 tests; the 3 test_deployed_addon_matches_repo cases fail while the installed add-in is older than the repo)
uv run ruff check  # lint
```

## Key files

- `src/fusion360_mcp/server.py` — MCP server entry point (click CLI, `build_server`), resources, prompts
- `src/fusion360_mcp/tools.py` — the registry: assembles the toolset modules, expands annotation flags, looks tools up by name
- `src/fusion360_mcp/toolsets/<toolset>.py` — one module per toolset: `TOOLS` (schemas with annotation flags inline) and `MOCKS`
- `src/fusion360_mcp/toolset_state.py` — enabled toolsets per server, `--toolsets` parsing, the `fusion_toolsets` reply
- `src/fusion360_mcp/mock.py` — mock envelope for `--mode mock` (`ok`, deltas, `__mock_error__`)
- `src/fusion360_mcp/connection.py` — TCP client to Fusion add-in
- `src/fusion360_mcp/hints.py` — error-classification table (mirror of `addon/server/hints.py`)
- `addon/server/command_handler.py` — add-in handlers and the `_COMMANDS` dispatch dict; `addon/server/ecad.py` for electronics, `addon/server/drawing.py` for drawings, `addon/server/documents.py` for the open-document helpers both use
- `scripts/verify_bridge.py` — live check over the socket: ping, sketch, rectangle, extrude, read back a 30 cm³ body
- `tests/` — tool registry, toolsets, add-in wiring, mocks, server routing, connection, annotations; `tests/fixtures/tool_schemas_baseline.json` freezes every schema

## Toolsets

Every tool belongs to exactly one toolset (the module it is defined in). Only enabled toolsets are listed. Default: `core,modeling,inspection` (50 tools). Change it with `--toolsets` (comma list or `all`) or `FUSION_MCP_TOOLSETS`; agents switch at runtime with `fusion_toolsets`, which sends `notifications/tools/list_changed`. `core` is always on.

Clients that run unattended (scripts, other projects' agents) should set `FUSION_MCP_TOOLSETS` to the toolsets they need instead of relying on enabling them at runtime.

| Toolset | Tools | Contents |
|---|---:|---|
| `core` | 15 | ping, get_scene_info, get_object_info, list_components, get/set_design_type, undo, execute_code, render_view, export, import_mesh, docs_list/activate/open, fusion_toolsets |
| `modeling` | 29 | sketch tools, constraints, dimensions, offset/trim/extend_curve, project_geometry; extrude, revolve, fillet, chamfer, shell, mirror, create_hole, rectangular/circular_pattern; boolean_operation, move_body, rename_body; get/create/set/delete_parameter |
| `inspection` | 6 | measure_distance, measure_angle, get_bounding_box, get_physical_properties, create_section_analysis, check_interference |
| `modeling_advanced` | 23 | sweep, loft, create_thread, draft_faces, split_body, split_face, offset_faces, scale_body, suppress/unsuppress_feature, create_box/_parametric/cylinder/sphere/torus, construction plane/axis, set_appearance, export_stl/step/f3d/view_sheet, delete_all |
| `assembly` | 4 | create_component, add_joint, create_as_built_joint, create_rigid_group |
| `surface_sheetmetal` | 9 | patch/stitch/thicken/ruled/trim surface, create_flange, create_bend, flat_pattern, unfold |
| `cam` | 8 | cam_* |
| `electronics` | 38 | ecad_* |
| `drawing` | 5 | drawing_info, drawing_create, drawing_autodim, drawing_tidy, drawing_export (ported from zerrk2.0's FusionDrawings add-in) |

`modeling_advanced` exists so the default list stays at 50 tools or fewer: putting all modeling tools in `modeling` would give 70. The parameter tools stay in `modeling` because parametric work and zerrk2.0's verifier/flex checks rely on them. Tests hold the default at ≤ 50 and `core` at ≤ 15; the default is at 50 now, so a new default tool means moving one out.

The `docs_*` tools are in `core` because every toolset needs document switching: drawing tools work on the active drawing, ecad tools on the active electronics document, everything else on the active design. Drawing handlers get the drawing by casting `app.activeDocument` to `DrawingDocument`; never through `_design()`, which raises on a drawing.

Deferred to PR3: FusionDrawings' UI and API ops (ui-commands, ui-run, text-command, api-introspect, api-doc) as `fusion_command`/`api_lookup`; its `exec` is covered by `execute_code`.

## Adding a new command

1. Add the handler method in the **add-in's** `command_handler.py` and its entry in the `_COMMANDS` dict (electronics: `ecad.py` and `EcadHandler.commands()`; drawings: `drawing.py` and `DrawingHandler.commands()`)
2. In the right `src/fusion360_mcp/toolsets/<toolset>.py`, add the schema dict to `TOOLS` (with `"annotations": READ_ONLY | IDEMPOTENT | DESTRUCTIVE` if it applies) and a mock handler to `MOCKS`
3. If it mutates the design, add it to both `CommandHandler._MUTATION_COMMANDS` and `mock._MUTATION_MOCKS`. Drawing and `docs_*` tools stay out: the body/mass snapshot reads the design, which a drawing does not have
4. Add a behaviour test in `tests/test_mock.py` (drawing and `docs_*`: `tests/test_drawing.py`). `test_toolset_wiring` already checks that the schema, the mock and the add-in handler all exist. Regenerate `tests/fixtures/tool_schemas_baseline.json` only when you mean to change a schema
5. The MCP server forwards tool calls 1:1 — no mapping code needed

## Conventions

- Tool names use snake_case and must match the add-in's command names exactly
- All Fusion API units are in **centimeters** (Fusion's internal unit); electronics uses millimetres
- The add-in uses newline-delimited JSON over TCP
- `ping` is the health check — it never touches the Fusion API
- Only mark a tool `idempotentHint` if re-sending it is harmless: `connection.py` retries those after a timeout. `drawing_create` is deliberately not idempotent, since every call writes a new cloud file
- Every tool has annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`)
- Every tool has a mock handler so `--mode mock` works without Fusion running
- `fusion_toolsets` is answered by the server and never reaches the add-in

## Testing in live Fusion

A command that blocks Fusion's main thread freezes the whole app, and nothing outside Fusion can recover it except killing the process. So:

- Drive Fusion through the add-in (TCP 9876), one step per call, each with a timeout: the client timeout, or the `LONG_COMMANDS` value (`addon/server/event_bridge.py`) for slow commands. Never run a multi-step script in the Text Commands palette: it runs on the main thread with no timeout and no way out.
- Test only in new, unsaved documents. Close every document the test opened with `close(False)` (without saving), also after a failure, and never open, change or save a real design.
- Report each step's result (passed, failed with its error, or timed out) rather than one overall verdict, so a hang points at the exact step.
- When a read might hang or crash Fusion, write a flushed log line before the read, so the last line names the culprit.
- If a modal dialog blocks Fusion, capture its text before dismissing it (`dialog_guard`) and report it.

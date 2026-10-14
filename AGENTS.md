# AGENTS.md

## Overview

This is an MCP server (136 Fusion tools in 9 toolsets, plus `fusion_toolsets`) that connects AI coding agents to Autodesk Fusion 360 for CAD automation. It consists of two pieces:

1. **MCP Server** (this repo) — speaks MCP protocol over stdio, forwards commands to Fusion via TCP
2. **Fusion 360 Add-in** — runs inside Fusion, executes commands on the main thread via CustomEvent bridge

## How the system works

```
Claude Code ──stdio──> MCP Server ──TCP :9876──> Fusion Add-in ──CustomEvent──> Main Thread
                                   <──JSON──                    <──result──
```

The add-in uses a CustomEvent + work queue pattern to safely dispatch all Fusion API calls to the main thread. Socket threads submit work items and block on a per-item `threading.Event` until the main thread completes execution.

## Toolsets: not every tool is listed

Tools are grouped into toolsets, and only enabled ones are listed. The default is `core,modeling,inspection` (50 tools). If a tool you need isn't in your list, it's in a disabled toolset:

- Call `fusion_toolsets` with no arguments to see every toolset, its tool count and whether it's on.
- Call `fusion_toolsets {"enable": ["cam"]}` to turn one on. `["all"]` turns on everything; `"disable"` turns toolsets off. `core` is always on.
- Calling a tool from a disabled toolset returns an error that names the exact `fusion_toolsets` call to make.

| Toolset | Default | Contents |
|---------|:-------:|----------|
| `core` | always | ping, scene/object info, list_components, design type, undo, execute_code, render_view, export, import_mesh, docs_list/activate/open, fusion_toolsets |
| `modeling` | yes | sketch tools, constraints, dimensions, curve edits, project_geometry; extrude, revolve, fillet, chamfer, shell, mirror, create_hole, patterns; boolean_operation, move_body, rename_body; get/create/set/delete_parameter |
| `inspection` | yes | measure_distance, measure_angle, get_bounding_box, get_physical_properties, create_section_analysis, check_interference |
| `modeling_advanced` | no | sweep, loft, create_thread, draft/split/offset/scale, suppress/unsuppress, direct primitives, construction plane/axis, set_appearance, export_stl/step/f3d/view_sheet, delete_all |
| `assembly` | no | create_component, add_joint, create_as_built_joint, create_rigid_group |
| `surface_sheetmetal` | no | surface and sheet-metal tools |
| `cam` | no | cam_* |
| `electronics` | no | ecad_* (lengths in mm) |
| `drawing` | no | drawing_* (info, create from a saved design, auto-dimension, tidy, PDF/DXF/DWG export) |

The server is started with `--toolsets` (comma list or `all`) or `FUSION_MCP_TOOLSETS` to change the default.

## Available tools

The tables below are grouped by function, not by toolset. Electronics (`ecad_*`) tools aren't listed here.

### Scene & Query
| Tool | Description |
|------|-------------|
| `ping` | Health check (no Fusion API, instant) |
| `get_scene_info` | Design name, bodies, sketches, features, camera |
| `get_object_info` | Detailed info about a named body or sketch |
| `list_components` | List all components in the design |

### Sketching
| Tool | Description |
|------|-------------|
| `create_sketch` | New sketch on xy/yz/xz, optional offset |
| `draw_rectangle` | Rectangle in most recent sketch |
| `draw_circle` | Circle in most recent sketch |
| `draw_line` | Line in most recent sketch |
| `draw_arc` | Arc (center + start + sweep angle) |
| `draw_spline` | Fit-point or control-point spline |
| `create_polygon` | Regular polygon (3–64 sides) |
| `add_constraint` | Geometric constraint (coincident, parallel, tangent, etc.) |
| `add_dimension` | Driving dimension (distance, angle, radial, diameter) |
| `offset_curve` | Offset connected sketch curves |
| `trim_curve` | Trim at intersections |
| `extend_curve` | Extend to nearest intersection |
| `project_geometry` | Project edges/bodies onto sketch plane |

### Features
| Tool | Description |
|------|-------------|
| `extrude` | Extrude a sketch profile |
| `revolve` | Revolve a profile around an axis |
| `sweep` | Sweep a profile along a path |
| `loft` | Loft between two or more profiles |
| `fillet` | Round edges (all/top/bottom/vertical) |
| `chamfer` | Chamfer edges |
| `shell` | Hollow out a body |
| `mirror` | Mirror a body across a plane |
| `create_hole` | Hole feature on a body face |
| `rectangular_pattern` | Pattern in rows and columns |
| `circular_pattern` | Pattern around an axis |
| `create_thread` | Threads (cosmetic or modeled) |
| `draft_faces` | Draft/taper for mold release |
| `split_body` | Split a body using a plane |
| `split_face` | Split faces of a body |
| `offset_faces` | Push/pull faces by a distance |
| `scale_body` | Scale uniformly or non-uniformly |
| `suppress_feature` | Suppress a timeline feature |
| `unsuppress_feature` | Re-enable a suppressed feature |

### Body Operations
| Tool | Description |
|------|-------------|
| `move_body` | Translate a body by (x, y, z) |
| `boolean_operation` | Join/cut/intersect two bodies |
| `delete_all` | Clear the design |
| `undo` | Undo last operation |

### Direct Primitives
| Tool | Description |
|------|-------------|
| `create_box` | Box (via TemporaryBRepManager) |
| `create_cylinder` | Cylinder |
| `create_sphere` | Sphere |
| `create_torus` | Torus |

### Surface Operations
| Tool | Description |
|------|-------------|
| `patch_surface` | Patch surface from boundary edges |
| `stitch_surfaces` | Stitch surface bodies into one |
| `thicken_surface` | Thicken a surface into a solid |
| `ruled_surface` | Ruled surface from an edge |
| `trim_surface` | Trim a surface with another body |

### Sheet Metal
| Tool | Description |
|------|-------------|
| `create_flange` | Create a flange on an edge |
| `create_bend` | Add a bend |
| `flat_pattern` | Create flat pattern |
| `unfold` | Unfold specific bends |

### Construction Geometry
| Tool | Description |
|------|-------------|
| `create_construction_plane` | Offset, angle, midplane, 3-point, tangent |
| `create_construction_axis` | Two-point, intersection, edge, perpendicular |

### Assembly
| Tool | Description |
|------|-------------|
| `create_component` | Create a sub-assembly component |
| `add_joint` | Joint between two components |
| `create_as_built_joint` | Joint from current positions |
| `create_rigid_group` | Lock components together |

### Inspection & Analysis
| Tool | Description |
|------|-------------|
| `measure_distance` | Minimum distance between entities |
| `measure_angle` | Angle between entities |
| `get_physical_properties` | Mass, volume, area, center of mass |
| `create_section_analysis` | Section plane through model |
| `check_interference` | Detect collisions between components |

### Appearance & Parameters
| Tool | Description |
|------|-------------|
| `set_appearance` | Assign material appearance from library |
| `get_parameters` | List all user parameters |
| `create_parameter` | Create a new parameter |
| `set_parameter` | Update a parameter value |
| `delete_parameter` | Remove a parameter |

### Export
| Tool | Description |
|------|-------------|
| `export_stl` | Export body as STL |
| `export_step` | Export body as STEP |
| `export_f3d` | Export design as Fusion archive |

### CAM / Manufacturing
| Tool | Description |
|------|-------------|
| `cam_create_setup` | Create a manufacturing setup (milling/turning/cutting) |
| `cam_create_operation` | Add a machining operation (face, contour, adaptive, drilling, etc.) |
| `cam_generate_toolpath` | Generate toolpaths for operations |
| `cam_post_process` | Post-process to G-code (fanuc, grbl, haas, etc.) |
| `cam_list_setups` | List all manufacturing setups |
| `cam_list_operations` | List operations in a setup |
| `cam_get_operation_info` | Get operation details (strategy, tool, parameters) |

### Code Execution
| Tool | Description |
|------|-------------|
| `execute_code` | Run arbitrary Python in Fusion (REPL-style) |

### Perception
| Tool | Description |
|------|-------------|
| `render_view` | Capture the active viewport as a PNG. Pass `view=iso\|front\|top\|...` to reposition the camera first. Returns an image content block you can visually inspect to validate geometry before committing to more operations. |

## Response shape

Every tool call returns a dict-shaped result with these conventions — read them instead of guessing whether an operation worked:

**Success:**
```json
{
  "ok": true,
  "body_name": "Body1",   // tool-specific fields
  ...,
  "deltas": {             // present only for mutations
    "body_count_before": 0,
    "body_count_after":  1,
    "body_count_delta":  1,
    "mass_g_before": 0.0,
    "mass_g_after":  7.85,
    "mass_g_delta":  7.85,
    "bbox_before": null,
    "bbox_after":  {"min": [0,0,0], "max": [1,1,1]}
  }
}
```

**Failure (no exception — the error flows back as data):**
```json
{
  "ok": false,
  "error_kind":    "PROFILE_NOT_CLOSED",     // stable tag you can branch on
  "error_message": "No profiles in sketch",  // short human-readable
  "hints":  ["close the loop", "..."],        // contextual repair suggestions
  "traceback": "..."                         // full traceback for debugging
}
```

Known `error_kind` values: `PROFILE_NOT_CLOSED`, `SKETCH_NOT_FOUND`, `BODY_NOT_FOUND`, `SELF_INTERSECTION`, `REGEN_FAILED`, `BOOLEAN_NO_OP`, `INVALID_INPUT`, `NO_ACTIVE_DESIGN`, `DESIGN_TYPE_MISMATCH`, `TIMEOUT`, `UNKNOWN_COMMAND`, `UNKNOWN`.

**Use the deltas to sanity-check without a render.** A `boolean_operation` that reports `body_count_delta: 0, mass_g_delta: 0` did nothing — follow up with `check_interference` before retrying. An `extrude` that shifts mass by three orders of magnitude is probably using the wrong units.

**Use `render_view` sparingly** — it returns ~200KB–2MB of base64 image data. Render after a logical checkpoint (finished a feature, about to commit), not after every mutation. Deltas already tell you whether the feature *did* something; `render_view` tells you whether it did the *right* something.

## MCP protocol features

- **Tool annotations** — every tool is tagged `readOnlyHint`, `destructiveHint`, `idempotentHint` so clients can auto-approve safe operations
- **Resources** — `fusion360://status`, `fusion360://design`, `fusion360://parameters`
- **Resource templates** — `fusion360://body/{name}`, `fusion360://component/{name}`
- **Prompts** — `create-box`, `model-threaded-bolt`, `sheet-metal-enclosure` workflow templates
- **Structured errors** — `isError=True` when the add-in reports failures. Error results carry `error_kind`, `hints`, and a traceback so the agent can branch on failure mode rather than parsing prose (see _Response shape_ above).
- **Mock mode** — `--mode mock` returns test data without Fusion running
- **Toolsets** — `fusion_toolsets` changes which tools are listed and sends `notifications/tools/list_changed`

## Important constraints

- **One operation per tool call.** Never batch multiple operations — Fusion's API is not thread-safe and complex scripts crash the add-in.
- **No loops inside execute_code.** If you need to create 3 similar features, make 3 separate tool calls.
- **Keep execute_code under ~15 lines.** Prefer the dedicated tools over execute_code whenever possible.
- **Units are centimeters.** Fusion's internal API uses cm, not mm.
- **30-second timeout.** Commands that take longer than 30s will return a timeout error.
- **body_name preferred over body_index.** Use named lookups when possible.
- **Verify after each step.** Call `get_scene_info` or `get_object_info` to confirm success — don't assume from lack of error.
- **Name everything.** Name every body and sketch explicitly so they can be referenced reliably in later steps.

## Troubleshooting

- If commands fail with "Not connected", the Fusion add-in isn't running. The user needs to start it in Fusion (Shift+S > Add-Ins > Run).
- If commands time out, the Fusion main thread may be blocked (modal dialog, heavy computation).
- After any error, call `get_scene_info` to check if the operation partially applied before retrying.
- Logs are written to `~/fusion360mcp.log` by the add-in.

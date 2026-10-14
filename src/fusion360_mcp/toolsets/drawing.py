"""Drawing toolset: Fusion drawings (.f2d) of a saved design.

Info, automatic Create Drawing, auto-dimension, tidy and PDF/DXF/DWG
export.  Every tool works on the active document, which must be a drawing
(``drawing_create`` excepted); ``docs_list`` / ``docs_activate`` in core
switch documents.  Ported from zerrk2.0's FusionDrawings add-in.
"""

from collections.abc import Callable

from ..hints import classify as _classify
from ._flags import READ_ONLY

TOOLSET = "drawing"
SUMMARY = "Drawings (.f2d): create from a saved design, auto-dimension, tidy, export"

_ACTIVE = (
    " Works on the active document, which must be a drawing: use docs_list "
    "and docs_activate to switch to it."
)

_SHEET = {
    "type": "integer",
    "minimum": 0,
    "description": (
        "Sheet index from 0, as drawing_info lists them (default: the "
        "active sheet)"
    ),
}

_SETTINGS = {
    "type": "object",
    "additionalProperties": {"type": ["string", "number", "boolean"]},
    "description": (
        "Extra properties to set on the API input object, as "
        "{property: value}; dotted names walk sub-objects. A string that "
        "names an adsk.drawing enum member (e.g. 'A3SheetSize') is set as "
        "that member. Numbers are passed to the API unchanged, in its own "
        "units."
    ),
}

TOOLS: list[dict] = [
    {
        "name": "drawing_info",
        "title": "Drawing Info",
        "description": (
            "Summary of the active drawing: name, saved flag, cloud file id, "
            "and each sheet (index, name, active) with its views (index, "
            "type)." + _ACTIVE
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "drawing_create",
        "title": "Create Drawing",
        "description": (
            "Run Fusion's automatic Create Drawing on a design: creates a new "
            "drawing file in the design's cloud folder, laid out with views "
            "by Fusion. Uses the active design, which must be saved to the "
            "cloud, unless design_id is given. Each call creates another "
            "drawing file, so call it once and check docs_list before "
            "retrying after a timeout."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "design_id": {
                    "type": "string",
                    "description": (
                        "Cloud file id of the design (default: the active "
                        "document, which must be a saved design)"
                    ),
                },
                "template_id": {
                    "type": "string",
                    "description": "Cloud file id of a drawing template",
                },
                "open": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Open the new drawing and make it the active document"
                    ),
                },
                "settings": _SETTINGS,
            },
        },
    },
    {
        "name": "drawing_autodim",
        "title": "Auto-Dimension Drawing Views",
        "description": (
            "Run Fusion's auto-dimension (Sheet.autoDimension) on one view or "
            "every view of a sheet. Fusion chooses what to dimension and "
            "where, by the strategy, from the datum corner; the API cannot "
            "place a single chosen dimension. Run drawing_tidy afterwards to "
            "clear overlaps." + _ACTIVE
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sheet": _SHEET,
                "view": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "View index from 0 on the sheet, as drawing_info "
                        "lists them (default: every view)"
                    ),
                },
                "strategy": {
                    "type": "string",
                    "enum": [
                        "automatic",
                        "baseline",
                        "chain",
                        "ordinate",
                        "overall",
                        "symmetric",
                    ],
                    "description": (
                        "Dimension strategy (DimensionStrategyTypes); "
                        "default: Fusion's"
                    ),
                },
                "datum": {
                    "type": "string",
                    "enum": [
                        "bottom_left",
                        "bottom_right",
                        "top_left",
                        "top_right",
                    ],
                    "description": (
                        "Datum corner the dimensions run from "
                        "(DatumPositionsTypes); default: Fusion's"
                    ),
                },
                "settings": _SETTINGS,
            },
        },
    },
    {
        "name": "drawing_tidy",
        "title": "Tidy Drawing Sheet",
        "description": (
            "Run Fusion's tidy-up (Sheet.tidyUp) on a sheet: it re-arranges "
            "views, dimensions and labels to remove overlaps." + _ACTIVE
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sheet": _SHEET,
            },
        },
    },
    {
        "name": "drawing_export",
        "title": "Export Drawing",
        "description": (
            "Export the active drawing to PDF, DXF or DWG. Writes the file "
            "(replacing one already at path) and creates missing folders; "
            "the drawing itself is unchanged." + _ACTIVE
        ),
        "inputSchema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute file-system path of the output file",
                },
                "format": {
                    "type": "string",
                    "enum": ["pdf", "dxf", "dwg"],
                    "description": "Output format (default: from path's extension)",
                },
                "line_weights": {
                    "type": "boolean",
                    "description": "PDF only: print with line weights (default true)",
                },
                "sheet_range": {
                    "type": "string",
                    "description": (
                        "PDF only: sheets to export, e.g. '1-2' (default: all)"
                    ),
                },
            },
        },
    },
]


# ── mocks (--mode mock) ────────────────────────────────────────────────────

_MOCK_FILE_ID = "urn:adsk.wipprod:dm.lineage:mockdrawing"


def _error(message: str) -> dict:
    kind, hint_list = _classify(message)
    return {
        "ok": False,
        "error_kind": kind,
        "error_message": message,
        "hints": hint_list,
        "traceback": f"MockError: {message}",
    }


def _mock_sheets() -> list[dict]:
    return [
        {
            "index": 0,
            "name": "Sheet1",
            "active": True,
            "views": [
                {"index": 0, "type": "BaseViewType"},
                {"index": 1, "type": "ProjectedViewType"},
                {"index": 2, "type": "ProjectedViewType"},
            ],
        },
        {
            "index": 1,
            "name": "Sheet2",
            "active": False,
            "views": [{"index": 0, "type": "BaseViewType"}],
        },
    ]


def _sheet(p: dict) -> dict | None:
    sheets = _mock_sheets()
    index = p.get("sheet")
    if index is None:
        return sheets[0]
    return sheets[index] if 0 <= index < len(sheets) else None


def _no_sheet(index) -> dict:
    return _error(
        f"No sheet {index}: the drawing has 2 (indices from 0, see drawing_info)."
    )


def _drawing_info(_p: dict) -> dict:
    sheets = _mock_sheets()
    return {
        "name": "MockDesign Drawing v1",
        "saved": True,
        "file_id": _MOCK_FILE_ID,
        "sheet_count": len(sheets),
        "sheets": sheets,
    }


def _drawing_create(p: dict) -> dict:
    out = {
        "name": "MockDesign Drawing",
        "file_id": _MOCK_FILE_ID,
        "design": "MockDesign",
        "applied": dict(p.get("settings") or {}),
    }
    if p.get("open"):
        out["opened"] = {
            "name": "MockDesign Drawing v1",
            "kind": "drawing",
            "active": True,
            "saved": True,
            "file_id": _MOCK_FILE_ID,
        }
    return out


def _drawing_autodim(p: dict) -> dict:
    sheet = _sheet(p)
    if sheet is None:
        return _no_sheet(p.get("sheet"))
    count = len(sheet["views"])
    view = p.get("view")
    if view is not None and not 0 <= view < count:
        return _error(
            f"No view {view} on sheet {sheet['name']!r}: it has {count} "
            "(indices from 0, see drawing_info)."
        )
    picked = [view] if view is not None else list(range(count))
    results = [{"view": j, "ok": True} for j in picked]
    return {"sheet": sheet["name"], "dimensioned": len(results), "results": results}


def _drawing_tidy(p: dict) -> dict:
    sheet = _sheet(p)
    if sheet is None:
        return _no_sheet(p.get("sheet"))
    return {"sheet": sheet["name"], "tidied": True}


def _drawing_export(p: dict) -> dict:
    path = p.get("path", "C:/temp/MockDesign Drawing.pdf")
    fmt = (p.get("format") or path.rsplit(".", 1)[-1]).lower()
    if fmt not in ("pdf", "dxf", "dwg"):
        return _error(
            f"format must be pdf, dxf or dwg (got {fmt!r}); pass format or "
            "give path one of those extensions."
        )
    return {"exported": True, "path": path, "format": fmt, "bytes": 2048}


MOCKS: dict[str, Callable[[dict], dict]] = {
    "drawing_info": _drawing_info,
    "drawing_create": _drawing_create,
    "drawing_autodim": _drawing_autodim,
    "drawing_tidy": _drawing_tidy,
    "drawing_export": _drawing_export,
}

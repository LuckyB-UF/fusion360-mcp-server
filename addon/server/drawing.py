"""
Fusion Drawing handlers (.f2d): info, create, auto-dimension, tidy, export.

Ported from zerrk2.0's FusionDrawings add-in (``fd_handlers.py``), which
served the same ops over its own HTTP server; here they run over this
add-in's socket and EventBridge like every other command.

Nothing in this file goes through ``CommandHandler._design()`` or
``activeProduct``: a Drawing document has no Design product, and
``_design()`` raises on one.  The drawing comes from casting
``app.activeDocument`` to ``adsk.drawing.DrawingDocument``.

Member names are as read live from Fusion 2705.1.25 on 2026-10-09.  The API
has no call to place one chosen dimension; ``Sheet.autoDimension`` is the
only one.  All methods run on Fusion's main thread (dispatched by
EventBridge).
"""

from __future__ import annotations

import os

import adsk.core

from . import documents as _docs
from . import get_logger

try:  # the Drawing API is missing from older Fusion builds
    import adsk.drawing as drawing
except Exception:  # pragma: no cover - older Fusion
    drawing = None

log = get_logger("drawing")

_FORMATS = ("pdf", "dxf", "dwg")


class DrawingError(RuntimeError):
    """Raised for drawing-specific failures (classified by hints)."""


# ----------------------------------------------------------------------
# enum helpers
# ----------------------------------------------------------------------


def _enum_members(cls) -> dict:
    return {
        name: getattr(cls, name)
        for name in dir(cls)
        if not name.startswith("_") and isinstance(getattr(cls, name), int)
    }


def _member(cls, text: str):
    """Enum member by name prefix, ignoring case and underscores:
    ``("bottom_left", DatumPositionsTypes)`` finds ``BottomLeft...``."""
    want = text.replace("_", "").lower()
    members = _enum_members(cls)
    for name, value in members.items():
        if name.lower().startswith(want):
            return value
    raise ValueError(
        f"{text!r} is not one of {', '.join(sorted(members))} "
        f"({cls.__name__} in this Fusion build)"
    )


def _enum_name(cls, value):
    for name, member in _enum_members(cls).items():
        if member == value:
            return name
    return value


def _enum_value(text: str):
    """A bare enum member name (e.g. ``A3SheetSize``), looked up in every
    class of adsk.drawing."""
    for cls_name in dir(drawing):
        cls = getattr(drawing, cls_name)
        if isinstance(cls, type) and hasattr(cls, text):
            value = getattr(cls, text)
            if isinstance(value, int):
                return value
    return None


def _apply_settings(obj, settings: dict | None) -> dict:
    """Set ``prop: value`` pairs on an API input object.

    Dotted props walk sub-objects.  JSON numbers and booleans are set as
    they are; a string that names an adsk.drawing enum member is set as
    that member, any other string as the string.
    """
    applied = {}
    for key, raw in (settings or {}).items():
        target = obj
        parts = key.split(".")
        for part in parts[:-1]:
            target = getattr(target, part)
        if not hasattr(target, parts[-1]):
            raise DrawingError(
                f"{type(target).__name__} has no property {parts[-1]!r} "
                f"(settings key {key!r})"
            )
        value = raw
        if isinstance(raw, str):
            member = _enum_value(raw)
            if member is not None:
                value = member
        setattr(target, parts[-1], value)
        applied[key] = raw
    return applied


# ----------------------------------------------------------------------
# handler
# ----------------------------------------------------------------------


class DrawingHandler:
    """The ``drawing_*`` commands.  Instantiated once by CommandHandler."""

    def __init__(self, app: adsk.core.Application):
        self.app = app

    def commands(self) -> dict:
        return {
            "drawing_info": self.info,
            "drawing_create": self.create,
            "drawing_autodim": self.autodim,
            "drawing_tidy": self.tidy,
            "drawing_export": self.export,
        }

    # -- helpers -------------------------------------------------------

    def _require_api(self):
        if drawing is None:
            raise DrawingError(
                "This Fusion build has no Drawing API (adsk.drawing); "
                "update Fusion."
            )

    def _drawing(self):
        """The active document's Drawing.  Never via _design()."""
        self._require_api()
        doc = self.app.activeDocument
        ddoc = drawing.DrawingDocument.cast(doc) if doc else None
        if not ddoc:
            kind = _docs.doc_kind(doc) if doc else "no"
            raise DrawingError(
                f"The active document is a {kind} document, not a drawing. "
                "Call docs_list, then docs_activate with the drawing's name."
            )
        return ddoc.drawing

    @staticmethod
    def _sheets(dwg):
        sheets = getattr(dwg, "sheets", None)
        if sheets is None:
            raise DrawingError(
                "This Fusion build has no Drawing.sheets (added in the 2026 "
                "Drawing API releases); update Fusion."
            )
        return sheets

    def _sheet(self, dwg, sheet):
        if sheet is None:
            return dwg.activeSheet
        sheets = self._sheets(dwg)
        index = int(sheet)
        if not 0 <= index < sheets.count:
            raise DrawingError(
                f"No sheet {index}: the drawing has {sheets.count} "
                "(indices from 0, see drawing_info)."
            )
        return sheets.item(index)

    @staticmethod
    def _view_type(view):
        # View.type throws "InternalValidationError : pAsset" on an
        # automatic drawing (2705.1.25).
        try:
            return _enum_name(drawing.ViewTypes, view.type)
        except RuntimeError as exc:
            return f"unreadable ({exc})"

    # -- commands ------------------------------------------------------

    def info(self):
        """Sheets of the active drawing and each one's views by type."""
        dwg = self._drawing()
        doc = self.app.activeDocument
        # Drawing.parentDocument throws InternalValidationError on a freshly
        # created drawing, so the document comes from activeDocument.
        summary = _docs.doc_info(doc, doc)
        sheets = self._sheets(dwg)
        active = dwg.activeSheet
        out = []
        for i in range(sheets.count):
            sheet = sheets.item(i)
            views = [
                {"index": j, "type": self._view_type(sheet.views.item(j))}
                for j in range(sheet.views.count)
            ]
            out.append({
                "index": i,
                "name": sheet.name,
                "active": sheet == active,
                "views": views,
            })
        return {
            "name": summary["name"],
            "saved": summary["saved"],
            "file_id": summary["file_id"],
            "sheet_count": len(out),
            "sheets": out,
        }

    def create(self, design_id: str = None, template_id: str = None,
               open: bool = False, settings: dict = None):
        """Fusion's automatic Create Drawing, from the active saved design or
        a design file id, optionally from a template file id."""
        self._require_api()
        if design_id:
            design_file = _docs.find_cloud_file(self.app, design_id)
        else:
            doc = self.app.activeDocument
            kind = _docs.doc_kind(doc) if doc else "no"
            if kind != "fusion":
                raise DrawingError(
                    f"The active document is a {kind} document, not a design. "
                    "Call docs_activate with the design's name, or pass "
                    "design_id."
                )
            if not doc.isSaved or not doc.dataFile:
                raise DrawingError(
                    "Save the design to the cloud first: drawing_create needs "
                    "its cloud file."
                )
            design_file = doc.dataFile

        manager = drawing.DrawingManager.get()
        inp = manager.createDrawingInput(
            design_file,
            drawing.DrawingCreationModes.AutomaticDrawingCreationMode,
        )
        if template_id:
            template = _docs.find_cloud_file(self.app, template_id)
            # templateFile is ignored unless baseDocumentType says FromTemplate.
            inp.baseDocumentType = (
                drawing.BaseDocumentTypes.FromTemplateBaseDocumentType
            )
            inp.templateFile = template
        applied = _apply_settings(inp, settings)

        log.info("createDrawing from %s", design_file.name)
        created = manager.createDrawing(inp)
        if not created:
            raise DrawingError("DrawingManager.createDrawing returned nothing")
        out = {
            "name": created.name,
            "file_id": created.id,
            "design": design_file.name,
            "applied": applied,
        }
        if open:
            doc = self.app.documents.open(created, True)
            out["opened"] = _docs.doc_info(doc, self.app.activeDocument)
        return out

    def autodim(self, sheet: int = None, view: int = None,
                strategy: str = None, datum: str = None,
                settings: dict = None):
        """Sheet.autoDimension, one view at a time.  Fusion places the
        dimensions by the strategy from the datum corner."""
        dwg = self._drawing()
        target = self._sheet(dwg, sheet)
        views = target.views
        if views.count == 0:
            raise DrawingError(f"Sheet {target.name!r} has no views.")
        if view is not None:
            index = int(view)
            if not 0 <= index < views.count:
                raise DrawingError(
                    f"No view {index} on sheet {target.name!r}: it has "
                    f"{views.count} (indices from 0, see drawing_info)."
                )
            picked = [index]
        else:
            picked = list(range(views.count))
        # Resolve the enums before touching the sheet, so a bad name fails
        # without dimensioning half the views.
        strategy_value = (
            _member(drawing.DimensionStrategyTypes, strategy)
            if strategy else None
        )
        datum_value = (
            _member(drawing.DatumPositionsTypes, datum) if datum else None
        )
        results = []
        for j in picked:
            inp = target.createAutoDimensionInput()
            if inp is None:
                raise DrawingError("Sheet.createAutoDimensionInput returned null")
            inp.view = views.item(j)
            if strategy_value is not None:
                inp.dimensionStrategy = strategy_value
            if datum_value is not None:
                inp.datumLocation = datum_value
            _apply_settings(inp, settings)
            results.append({"view": j, "ok": bool(target.autoDimension(inp))})
        return {
            "sheet": target.name,
            "dimensioned": sum(r["ok"] for r in results),
            "results": results,
        }

    def tidy(self, sheet: int = None):
        """Sheet.tidyUp: Fusion re-arranges views, dimensions and labels to
        remove overlaps."""
        target = self._sheet(self._drawing(), sheet)
        # On 2705.1.25 tidyUp is exposed as a property: reading it runs the
        # tidy and returns the bool.  Later builds may make it a method.
        tidy = target.tidyUp
        done = tidy() if callable(tidy) else tidy
        return {"sheet": target.name, "tidied": bool(done)}

    def export(self, path: str, format: str = None,
               line_weights: bool = None, sheet_range: str = None):
        """Export the active drawing to PDF, DXF or DWG."""
        dwg = self._drawing()
        if not os.path.isabs(path):
            raise DrawingError(f"path must be absolute, got {path!r}")
        fmt = (format or os.path.splitext(path)[1].lstrip(".")).lower()
        if fmt not in _FORMATS:
            raise DrawingError(
                f"format must be pdf, dxf or dwg (got {fmt or 'none'!r}); "
                "pass format or give path one of those extensions."
            )
        if fmt != "pdf" and (line_weights is not None or sheet_range):
            raise DrawingError("line_weights and sheet_range apply to pdf only")
        # Fusion fails on a missing folder.
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        mgr = dwg.exportManager
        if fmt == "pdf":
            opts = mgr.createPDFExportOptions(path)
            opts.openPDF = False
            opts.useLineWeights = True if line_weights is None else bool(
                line_weights)
            if sheet_range:
                opts.sheetRange = sheet_range
        elif fmt == "dxf":
            opts = mgr.createDXFExportOptions(path)
        else:
            opts = mgr.createDWGExportOptions(path)
        log.info("drawing export %s -> %s", fmt, path)
        if not mgr.execute(opts):
            raise DrawingError(f"Fusion's drawing export to {fmt} returned false")
        size = os.path.getsize(path) if os.path.isfile(path) else None
        return {"exported": True, "path": path, "format": fmt, "bytes": size}

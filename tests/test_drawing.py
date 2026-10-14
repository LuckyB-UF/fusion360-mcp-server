"""The drawing toolset and the docs_* tools: mocks, add-in handlers, hints.

The add-in handlers (``addon/server/drawing.py`` and ``documents.py``) are
also run against a small fake of ``adsk`` so the ported logic executes
without Fusion: enum lookup, the tidyUp-as-property quirk, export paths.
"""

from __future__ import annotations

import ast
import importlib
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion360_mcp.connection import timeout_for
from fusion360_mcp.hints import classify
from fusion360_mcp.mock import _MUTATION_MOCKS, mock_command
from fusion360_mcp.tools import get_tool_by_name
from fusion360_mcp.toolsets import drawing as drawing_toolset

_ADDON = Path(__file__).resolve().parent.parent / "addon" / "server"
DRAWING_TOOLS = [t["name"] for t in drawing_toolset.TOOLS]
DOCS_TOOLS = ["docs_list", "docs_activate", "docs_open"]


# ── mocks ────────────────────────────────────────────────────────────


def test_drawing_info_lists_sheets_and_views():
    result = mock_command("drawing_info")
    assert result["ok"] is True
    assert result["sheet_count"] == len(result["sheets"])
    first = result["sheets"][0]
    assert set(first) == {"index", "name", "active", "views"}
    assert set(first["views"][0]) == {"index", "type"}


def test_drawing_create_reports_the_new_file_and_opens_on_request():
    result = mock_command("drawing_create", {"settings": {"sheetSize": "A3"}})
    assert result["file_id"].startswith("urn:")
    assert result["applied"] == {"sheetSize": "A3"}
    assert "opened" not in result
    opened = mock_command("drawing_create", {"open": True})["opened"]
    assert opened["kind"] == "drawing" and opened["active"] is True


def test_drawing_autodim_every_view_or_one():
    every = mock_command("drawing_autodim", {})
    assert [r["view"] for r in every["results"]] == [0, 1, 2]
    assert every["dimensioned"] == 3
    one = mock_command("drawing_autodim", {"view": 1, "strategy": "baseline"})
    assert one["results"] == [{"view": 1, "ok": True}]


def test_drawing_autodim_bad_view_is_an_error():
    result = mock_command("drawing_autodim", {"view": 9})
    assert result["ok"] is False
    assert "No view 9" in result["error_message"]


def test_drawing_tidy_names_the_sheet():
    assert mock_command("drawing_tidy", {"sheet": 1})["sheet"] == "Sheet2"
    assert mock_command("drawing_tidy", {"sheet": 5})["ok"] is False


def test_drawing_export_takes_the_format_from_the_extension():
    result = mock_command("drawing_export", {"path": "C:/out/a.DXF"})
    assert result["format"] == "dxf" and result["exported"] is True
    bad = mock_command("drawing_export", {"path": "C:/out/a.png"})
    assert bad["ok"] is False


@pytest.mark.parametrize("name", DRAWING_TOOLS + DOCS_TOOLS)
def test_no_design_deltas(name):
    """A body/mass snapshot means nothing on a drawing, so these tools stay
    out of both mutation sets."""
    assert name not in _MUTATION_MOCKS
    assert "deltas" not in mock_command(name, {})


# ── annotations and timeouts ─────────────────────────────────────────


def _ann(name: str) -> dict:
    return get_tool_by_name(name)["annotations"]


def test_annotations():
    for name in ("drawing_info", "docs_list"):
        assert _ann(name)["readOnlyHint"] is True
    # Not idempotent, so connection.py never re-sends them after a timeout:
    # a re-sent createDrawing made three drawings in FusionDrawings' history.
    for name in ("drawing_create", "drawing_autodim", "drawing_tidy",
                 "drawing_export", "docs_open"):
        ann = _ann(name)
        assert ann == {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        }, name
    assert _ann("docs_activate")["idempotentHint"] is True


def test_drawing_create_says_it_writes_a_cloud_file():
    desc = get_tool_by_name("drawing_create")["description"]
    assert "creates a new drawing file in the design's cloud folder" in desc


def test_slow_commands_get_long_timeouts():
    for name in ("drawing_create", "drawing_export", "docs_open"):
        assert timeout_for(name) > 60


# ── hints ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "message",
    [
        "The active document is a fusion document, not a drawing. Call "
        "docs_list, then docs_activate with the drawing's name.",
        "The active document is a drawing document, not a design. Call "
        "docs_activate with the design's name, or pass design_id.",
    ],
)
def test_wrong_document_kind_is_classified(message):
    kind, hints = classify(message)
    assert kind == "WRONG_DOCUMENT_KIND"
    assert any("docs_activate" in h for h in hints)


def test_unsaved_design_is_classified():
    kind, hints = classify(
        "Save the design to the cloud first: drawing_create needs its cloud "
        "file."
    )
    assert kind == "DESIGN_NOT_SAVED"
    assert any("design_id" in h for h in hints)


@pytest.mark.parametrize(
    "message",
    [
        "InternalValidationError : pAsset",
        "No sheet 3: the drawing has 1 (indices from 0, see drawing_info).",
        "Fusion's drawing export to pdf returned false",
        "'Chainx' is not one of A, B (DimensionStrategyTypes in this build)",
        "The active document is a other document, not a drawing.",
    ],
)
def test_drawing_failures_are_not_design_product_errors(message):
    assert classify(message)[0] not in ("NO_DESIGN_PRODUCT", "NO_ACTIVE_DESIGN")


def test_docs_errors_are_classified():
    assert classify("No open document named 'x'. Open documents: 'a'")[0] == (
        "DOCUMENT_NOT_FOUND"
    )
    assert classify("No cloud file with id 'urn:x'")[0] == "CLOUD_FILE_NOT_FOUND"


# ── add-in source ────────────────────────────────────────────────────


def _method_params(path: Path, cls_name: str) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        if cls.name == cls_name:
            return {
                fn.name: {a.arg for a in fn.args.args[1:]}
                for fn in cls.body
                if isinstance(fn, ast.FunctionDef)
            }
    raise AssertionError(f"{cls_name} not in {path.name}")


def _schema(name: str) -> tuple[set[str], set[str]]:
    schema = get_tool_by_name(name)["inputSchema"]
    return set(schema.get("properties", {})), set(schema.get("required", []))


def test_drawing_schemas_match_handler_arguments():
    """Dispatch is handler(**params): every schema property must be an
    argument, and every required argument a required property."""
    params = _method_params(_ADDON / "drawing.py", "DrawingHandler")
    methods = {f"drawing_{m}": m for m in
               ("info", "create", "autodim", "tidy", "export")}
    for tool, method in methods.items():
        props, required = _schema(tool)
        assert props == params[method], tool
        assert required <= params[method], tool


def test_docs_schemas_match_handler_arguments():
    params = _method_params(_ADDON / "command_handler.py", "CommandHandler")
    for tool in DOCS_TOOLS:
        props, _ = _schema(tool)
        assert props == params[tool], tool


def test_drawing_handlers_never_reach_for_a_design():
    """_design() raises on a Drawing document, and activeProduct is no
    design there either."""
    tree = ast.parse((_ADDON / "drawing.py").read_text(encoding="utf-8"))
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    used |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not used & {"_design", "_root", "activeProduct", "rootComponent"}


def test_drawing_tools_are_not_addon_mutation_commands():
    tree = ast.parse((_ADDON / "command_handler.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(
                node.targets[0], "id", "") == "_MUTATION_COMMANDS":
            names = set(ast.literal_eval(node.value.args[0]))
            break
    else:
        raise AssertionError("_MUTATION_COMMANDS not found")
    assert not names & set(DRAWING_TOOLS + DOCS_TOOLS)


# ── the add-in handlers against a fake adsk ──────────────────────────


class _Enum:
    pass


def _enum(name: str, **members: int) -> type:
    return type(name, (_Enum,), members)


class FakeDoc:
    def __init__(self, name, kind="fusion", saved=True, file_id="urn:d",
                 drawing=None):
        self.name = name
        self.kind = kind
        self.isSaved = saved
        self.dataFile = SimpleNamespace(id=file_id, name=name) if saved else None
        self.drawing = drawing
        self.objectType = {
            "fusion": "adsk::fusion::FusionDocument",
            "drawing": "adsk::drawing::DrawingDocument",
            "electronics": "adsk::electron::EcadDesignDocument",
        }.get(kind, "adsk::core::Document")
        self.activated = False

    def activate(self):
        self.activated = True


class FakeCollection:
    def __init__(self, items):
        self._items = list(items)

    @property
    def count(self):
        return len(self._items)

    def item(self, i):
        return self._items[i]


class FakeSheet:
    def __init__(self, name, views, tidy_as_property=True):
        self.name = name
        self.views = FakeCollection(views)
        self.autodims = []
        self._tidy_as_property = tidy_as_property
        self.tidied = 0

    def createAutoDimensionInput(self):
        return SimpleNamespace(view=None, dimensionStrategy=None,
                               datumLocation=None)

    def autoDimension(self, inp):
        self.autodims.append(inp)
        return True

    @property
    def tidyUp(self):
        if self._tidy_as_property:
            self.tidied += 1
            return True

        def run():
            self.tidied += 1
            return True
        return run


class FakeExportManager:
    def __init__(self):
        self.executed = []

    def createPDFExportOptions(self, path):
        return SimpleNamespace(kind="pdf", path=path, openPDF=True,
                               useLineWeights=None, sheetRange=None)

    def createDXFExportOptions(self, path):
        return SimpleNamespace(kind="dxf", path=path)

    def createDWGExportOptions(self, path):
        return SimpleNamespace(kind="dwg", path=path)

    def execute(self, opts):
        Path(opts.path).write_bytes(b"%PDF-fake")
        self.executed.append(opts)
        return True


class FakeManager:
    def __init__(self):
        self.created = []

    def createDrawingInput(self, design_file, mode):
        return SimpleNamespace(design=design_file, mode=mode,
                               baseDocumentType=None, templateFile=None,
                               sheetSize=None, isAutoDimension=None)

    def createDrawing(self, inp):
        self.created.append(inp)
        return SimpleNamespace(name=inp.design.name + " Drawing", id="urn:new")


@pytest.fixture
def addon(monkeypatch):
    """Import addon/server/{documents,drawing}.py against a fake adsk."""
    manager = FakeManager()
    drawing_mod = types.ModuleType("adsk.drawing")
    drawing_mod.DrawingDocument = SimpleNamespace(
        cast=lambda d: d if getattr(d, "kind", None) == "drawing" else None)
    drawing_mod.DrawingManager = SimpleNamespace(get=lambda: manager)
    drawing_mod.DrawingCreationModes = _enum(
        "DrawingCreationModes", AutomaticDrawingCreationMode=0)
    drawing_mod.BaseDocumentTypes = _enum(
        "BaseDocumentTypes", FromTemplateBaseDocumentType=1)
    drawing_mod.DimensionStrategyTypes = _enum(
        "DimensionStrategyTypes", BaselineDimensionStrategy=1,
        ChainDimensionStrategy=2)
    drawing_mod.DatumPositionsTypes = _enum(
        "DatumPositionsTypes", BottomLeftDatumPosition=0,
        TopRightDatumPosition=3)
    drawing_mod.ViewTypes = _enum("ViewTypes", BaseViewType=0)
    drawing_mod.SheetSizes = _enum("SheetSizes", A3SheetSize=7)
    fusion_mod = types.ModuleType("adsk.fusion")
    fusion_mod.FusionDocument = SimpleNamespace(
        cast=lambda d: d if getattr(d, "kind", None) == "fusion" else None)
    core_mod = types.ModuleType("adsk.core")
    core_mod.Application = object
    adsk = types.ModuleType("adsk")
    adsk.core, adsk.fusion, adsk.drawing = core_mod, fusion_mod, drawing_mod
    pkg = types.ModuleType("_fake_addon_server")
    pkg.__path__ = [str(_ADDON)]
    pkg.get_logger = lambda name=None: logging.getLogger(f"test.{name}")
    for name, mod in {
        "adsk": adsk,
        "adsk.core": core_mod,
        "adsk.fusion": fusion_mod,
        "adsk.drawing": drawing_mod,
        "_fake_addon_server": pkg,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    for sub in ("documents", "drawing"):
        monkeypatch.delitem(sys.modules, f"_fake_addon_server.{sub}", raising=False)
    drawing_py = importlib.import_module("_fake_addon_server.drawing")
    documents_py = importlib.import_module("_fake_addon_server.documents")
    return SimpleNamespace(drawing=drawing_py, documents=documents_py,
                           manager=manager)


def _app(docs, active):
    return SimpleNamespace(
        activeDocument=active,
        documents=SimpleNamespace(
            count=len(docs), item=lambda i: docs[i],
            open=lambda f, visible: FakeDoc(f.name + " v1", kind="drawing")),
        data=SimpleNamespace(findFileById=lambda i: (
            SimpleNamespace(id=i, name="Design") if i.startswith("urn:") else None)),
        version="2705.1.25",
    )


def _drawing_doc(sheets=None):
    sheets = sheets or [FakeSheet("Sheet1", [SimpleNamespace(type=0)] * 2)]
    dwg = SimpleNamespace(sheets=FakeCollection(sheets), activeSheet=sheets[0],
                          exportManager=FakeExportManager())
    return FakeDoc("Part Drawing v1", kind="drawing", drawing=dwg)


def test_doc_kind_covers_every_kind(addon):
    kind = addon.documents.doc_kind
    assert kind(FakeDoc("a")) == "fusion"
    assert kind(FakeDoc("a", kind="drawing")) == "drawing"
    assert kind(FakeDoc("a", kind="electronics")) == "electronics"
    assert kind(FakeDoc("a", kind="cam")) == "other"
    assert kind(None) == "other"


def test_find_open_matches_version_suffix_and_lists_names(addon):
    docs = [FakeDoc("Bracket v3"), FakeDoc("Bracketry v1")]
    app = _app(docs, docs[0])
    assert addon.documents.find_open(app, "Bracket") is docs[0]
    with pytest.raises(LookupError, match="'Bracket v3', 'Bracketry v1'"):
        addon.documents.find_open(app, "Nope")


def test_drawing_ops_refuse_a_design_document(addon):
    design = FakeDoc("Part v1")
    handler = addon.drawing.DrawingHandler(_app([design], design))
    for call in (handler.info, handler.tidy, handler.autodim):
        with pytest.raises(addon.drawing.DrawingError) as exc:
            call()
        assert classify(str(exc.value))[0] == "WRONG_DOCUMENT_KIND"


def test_info_reads_sheets_and_views(addon):
    doc = _drawing_doc()
    info = addon.drawing.DrawingHandler(_app([doc], doc)).info()
    assert info["name"] == "Part Drawing v1" and info["sheet_count"] == 1
    assert info["sheets"][0]["active"] is True
    assert info["sheets"][0]["views"] == [
        {"index": 0, "type": "BaseViewType"},
        {"index": 1, "type": "BaseViewType"},
    ]


def test_create_from_active_design_with_template_and_settings(addon):
    design = FakeDoc("Part v1", file_id="urn:part")
    handler = addon.drawing.DrawingHandler(_app([design], design))
    out = handler.create(template_id="urn:tpl",
                         settings={"sheetSize": "A3SheetSize",
                                   "isAutoDimension": True})
    inp = addon.manager.created[-1]
    assert inp.design.id == "urn:part"
    assert inp.baseDocumentType == 1 and inp.templateFile.id == "urn:tpl"
    assert inp.sheetSize == 7 and inp.isAutoDimension is True
    assert out["file_id"] == "urn:new" and "opened" not in out


def test_create_refuses_an_unsaved_or_non_design_document(addon):
    unsaved = FakeDoc("Part", saved=False)
    handler = addon.drawing.DrawingHandler(_app([unsaved], unsaved))
    with pytest.raises(addon.drawing.DrawingError) as exc:
        handler.create()
    assert classify(str(exc.value))[0] == "DESIGN_NOT_SAVED"
    doc = _drawing_doc()
    with pytest.raises(addon.drawing.DrawingError, match="not a design"):
        addon.drawing.DrawingHandler(_app([doc], doc)).create()


def test_create_rejects_an_unknown_setting(addon):
    design = FakeDoc("Part v1")
    handler = addon.drawing.DrawingHandler(_app([design], design))
    with pytest.raises(addon.drawing.DrawingError, match="no property 'bogus'"):
        handler.create(settings={"bogus": 1})
    assert addon.manager.created == []


def test_autodim_resolves_snake_case_enums_per_view(addon):
    doc = _drawing_doc()
    sheet = doc.drawing.activeSheet
    handler = addon.drawing.DrawingHandler(_app([doc], doc))
    out = handler.autodim(strategy="chain", datum="top_right")
    assert out["dimensioned"] == 2
    assert [i.dimensionStrategy for i in sheet.autodims] == [2, 2]
    assert [i.datumLocation for i in sheet.autodims] == [3, 3]
    with pytest.raises(ValueError, match="BaselineDimensionStrategy"):
        handler.autodim(strategy="ordinate")
    with pytest.raises(addon.drawing.DrawingError, match="No view 5"):
        handler.autodim(view=5)


@pytest.mark.parametrize("as_property", [True, False])
def test_tidy_handles_tidyup_as_property_or_method(addon, as_property):
    sheet = FakeSheet("Sheet1", [], tidy_as_property=as_property)
    doc = _drawing_doc([sheet])
    out = addon.drawing.DrawingHandler(_app([doc], doc)).tidy(sheet=0)
    assert out == {"sheet": "Sheet1", "tidied": True}
    assert sheet.tidied == 1


def test_export_pdf_creates_folders_and_sets_options(addon, tmp_path):
    doc = _drawing_doc()
    handler = addon.drawing.DrawingHandler(_app([doc], doc))
    path = tmp_path / "new" / "deeper" / "sheet.pdf"
    out = handler.export(str(path), line_weights=False, sheet_range="1-2")
    opts = doc.drawing.exportManager.executed[-1]
    assert out["format"] == "pdf" and out["bytes"] == len(b"%PDF-fake")
    assert opts.openPDF is False and opts.useLineWeights is False
    assert opts.sheetRange == "1-2"


def test_export_rejects_relative_paths_and_pdf_options_on_dxf(addon, tmp_path):
    doc = _drawing_doc()
    handler = addon.drawing.DrawingHandler(_app([doc], doc))
    with pytest.raises(addon.drawing.DrawingError, match="absolute"):
        handler.export("out/sheet.pdf")
    with pytest.raises(addon.drawing.DrawingError, match="pdf only"):
        handler.export(str(tmp_path / "a.dxf"), sheet_range="1")
    out = handler.export(str(tmp_path / "a.dwg"))
    assert out["format"] == "dwg"

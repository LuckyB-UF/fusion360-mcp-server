"""
Open documents: what kind each is, and switching between them.

Shared by the ``docs_*`` handlers in ``command_handler.py`` and the drawing
handlers in ``drawing.py``.  Nothing here reads a Design product, so it works
while a drawing or an electronics document is the active one.
"""

from __future__ import annotations

import adsk.core
import adsk.fusion

try:  # the Drawing API is missing from older Fusion builds
    import adsk.drawing as drawing
except Exception:  # pragma: no cover - older Fusion
    drawing = None


def doc_kind(doc) -> str:
    """``fusion``, ``drawing``, ``electronics`` or ``other``."""
    if doc is None:
        return "other"
    try:
        object_type = doc.objectType or ""
    except Exception:
        object_type = ""
    # objectType is e.g. "adsk::drawing::DrawingDocument"; electronics
    # documents live in adsk::electron (design, schematic and board).
    if "electron" in object_type.lower():
        return "electronics"
    if object_type.endswith("::DrawingDocument") or (
        drawing is not None and drawing.DrawingDocument.cast(doc)
    ):
        return "drawing"
    if adsk.fusion.FusionDocument.cast(doc):
        return "fusion"
    return "other"


def _same(a, b) -> bool:
    try:
        return a is not None and b is not None and a == b
    except Exception:
        return False


def cloud_id(data_file):
    """The cloud file id (``urn:...``) of *data_file*, or None.

    Right after a save Fusion reports the document as saved, but until the
    upload finishes ``DataFile.id`` is a local cache path, which
    ``createDrawing`` and ``findFileById`` reject (seen on 2705.1.30).
    """
    if data_file is None:
        return None
    try:
        file_id = data_file.id or ""
        complete = getattr(data_file, "isComplete", True)
    except Exception:
        return None
    return file_id if file_id.startswith("urn:") and complete else None


def doc_info(doc, active=None) -> dict:
    """Name, kind, active and saved flags, and cloud file id of *doc*.

    ``uploading`` is true while a saved document's upload is unfinished;
    ``file_id`` stays null until then.
    """
    data_file = None
    try:
        data_file = doc.dataFile
    except Exception:
        pass
    try:
        saved = bool(doc.isSaved)
    except Exception:
        saved = False
    file_id = cloud_id(data_file)
    return {
        "name": doc.name,
        "kind": doc_kind(doc),
        "active": _same(doc, active),
        "saved": saved,
        "uploading": bool(saved and data_file is not None and file_id is None),
        "file_id": file_id,
    }


def open_documents(app: adsk.core.Application) -> list:
    docs = app.documents
    return [docs.item(i) for i in range(docs.count)]


def find_open(app: adsk.core.Application, name: str):
    """The open document called *name*, or ``name vN`` (Fusion's version
    suffix).  Raises LookupError naming the open documents."""
    docs = open_documents(app)
    for doc in docs:
        if doc.name == name or doc.name.startswith(name + " v"):
            return doc
    names = ", ".join(repr(d.name) for d in docs) or "none"
    raise LookupError(
        f"No open document named {name!r}. Open documents: {names}"
    )


def find_cloud_file(app: adsk.core.Application, file_id: str):
    data_file = app.data.findFileById(file_id)
    if not data_file:
        raise LookupError(f"No cloud file with id {file_id!r}")
    return data_file

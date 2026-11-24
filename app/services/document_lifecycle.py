from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.chroma_store import get_or_create_collection


def delete_document(db: Session, document_id: str) -> None:
    doc = db.get(Document, document_id)
    if doc is None:
        return

    collection = get_or_create_collection(doc.kb_id)
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == doc.id)).all()
    ids = [c.chroma_id for c in chunks]
    if ids:
        try:
            collection.delete(ids=ids)
        except Exception:
            pass

    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))

    settings = get_settings()
    if doc.storage_path:
        path = settings.data_dir / doc.storage_path
        if path.is_file():
            path.unlink(missing_ok=True)

    db.delete(doc)
    db.commit()

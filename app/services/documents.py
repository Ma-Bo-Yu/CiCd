from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document import Document, DocumentStatus


ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}


def save_upload_bytes(document: Document, filename: str, content: bytes) -> None:
    settings = get_settings()
    dest_dir = settings.data_dir / "uploads" / document.kb_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    dest = dest_dir / f"{document.id}_{safe_name}"
    dest.write_bytes(content)
    document.storage_path = str(dest.relative_to(settings.data_dir))
    document.filename = safe_name
    document.mime_type = (
        mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    )
    document.status = DocumentStatus.PROCESSING.value


def save_upload(document: Document, file: UploadFile, content: bytes | None = None) -> None:
    settings = get_settings()
    dest_dir = settings.data_dir / "uploads" / document.kb_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name
    dest = dest_dir / f"{document.id}_{safe_name}"
    data = content if content is not None else file.file.read()
    dest.write_bytes(data)
    document.storage_path = str(dest.relative_to(settings.data_dir))
    document.filename = safe_name
    mime = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    document.mime_type = mime
    document.status = DocumentStatus.PROCESSING.value


def validate_filename(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"仅支持 PDF、Markdown、纯文本，收到: {filename}")


def create_document_record(db: Session, kb_id: str, filename: str) -> Document:
    validate_filename(filename)
    doc = Document(
        kb_id=kb_id,
        filename=filename,
        mime_type="",
        storage_path="",
        status=DocumentStatus.PENDING.value,
    )
    db.add(doc)
    db.flush()
    return doc

from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.services.chroma_store import get_or_create_collection
from app.services.llm import LLMService


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def parse_pdf_pages(path: Path) -> list[tuple[str, dict]]:
    doc = pymupdf.open(path)
    pages: list[tuple[str, dict]] = []
    for i, page in enumerate(doc, start=1):
        content = page.get_text().strip()
        if content:
            pages.append((content, {"page": i}))
    doc.close()
    return pages


def parse_markdown(path: Path) -> list[tuple[str, dict]]:
    raw = path.read_text(encoding="utf-8")
    sections: list[tuple[str, dict]] = []
    current_heading = None
    buf: list[str] = []
    for line in raw.splitlines():
        if line.startswith("#"):
            if buf:
                sections.append(("\n".join(buf), {"heading": current_heading or ""}))
                buf = []
            current_heading = line.lstrip("#").strip()
            buf.append(line)
        else:
            buf.append(line)
    if buf:
        sections.append(("\n".join(buf), {"heading": current_heading or ""}))
    if not sections and raw.strip():
        sections.append((raw, {}))
    return sections


def parse_txt(path: Path) -> list[tuple[str, dict]]:
    return [(path.read_text(encoding="utf-8"), {})]


def split_document(path: Path, filename: str) -> list[tuple[str, dict]]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return parse_pdf_pages(path)
    if lower.endswith(".md") or lower.endswith(".markdown"):
        return parse_markdown(path)
    if lower.endswith(".txt"):
        return parse_txt(path)
    raise ValueError(f"不支持的文件格式: {filename}")


class IngestService:
    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.llm = llm or LLMService()
        self.settings = get_settings()

    def _clear_existing_chunks(self, document: Document) -> None:
        collection = get_or_create_collection(document.kb_id)
        chunk_rows = self.db.scalars(
            select(Chunk).where(Chunk.document_id == document.id)
        ).all()
        ids = [c.chroma_id for c in chunk_rows]
        if ids:
            try:
                collection.delete(ids=ids)
            except Exception:
                pass
        self.db.execute(delete(Chunk).where(Chunk.document_id == document.id))

    async def ingest_document(self, document_id: str) -> None:
        document = self.db.get(Document, document_id)
        if document is None:
            return

        document.status = DocumentStatus.PROCESSING.value
        document.error_message = None
        self.db.commit()

        try:
            path = self.settings.data_dir / document.storage_path
            if not path.is_file():
                raise FileNotFoundError(f"文件不存在: {document.storage_path}")

            self._clear_existing_chunks(document)

            sections = split_document(path, document.filename)
            settings = self.settings
            pieces: list[tuple[str, dict]] = []
            for text, meta in sections:
                for piece in _chunk_text(text, settings.chunk_size, settings.chunk_overlap):
                    if piece.strip():
                        pieces.append((piece, meta))

            if not pieces:
                raise ValueError("未能从文档中提取文本")

            texts = [p[0] for p in pieces]
            embeddings = await self.llm.embed_texts(texts)
            collection = get_or_create_collection(document.kb_id)

            chroma_ids: list[str] = []
            metadatas: list[dict] = []
            for i, (text, meta) in enumerate(pieces):
                chunk = Chunk(
                    document_id=document.id,
                    kb_id=document.kb_id,
                    text=text,
                    metadata_json=json.dumps(meta, ensure_ascii=False),
                    chroma_id=f"{document.id}_{i}",
                )
                self.db.add(chunk)
                self.db.flush()
                chroma_ids.append(chunk.chroma_id)
                meta_row = {
                    "kb_id": document.kb_id,
                    "document_id": document.id,
                    "chunk_id": chunk.id,
                    "document_name": document.filename,
                    **{k: v for k, v in meta.items() if v},
                }
                metadatas.append(meta_row)

            collection.add(
                ids=chroma_ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )

            document.status = DocumentStatus.INDEXED.value
            self.db.commit()
        except Exception as exc:
            document.status = DocumentStatus.FAILED.value
            document.error_message = str(exc)
            self.db.commit()

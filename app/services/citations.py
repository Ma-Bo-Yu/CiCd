from __future__ import annotations

import json
from typing import Any

from app.models.chunk import Chunk
from app.models.document import Document
from app.services.text_utils import strip_html


def excerpt(text: str, limit: int = 200) -> str:
    t = strip_html(text)
    if len(t) <= limit:
        return t
    return t[:limit] + "…"


def build_citation(
    chunk: Chunk,
    document: Document,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "document_id": document.id,
        "document_name": document.filename,
        "chunk_id": chunk.id,
        "excerpt": excerpt(chunk.text),
    }
    if "page" in metadata:
        item["page"] = metadata["page"]
    if "heading" in metadata:
        item["heading"] = metadata["heading"]
    return item


def citations_to_json(citations: list[dict[str, Any]]) -> str:
    return json.dumps(citations, ensure_ascii=False)


def citations_from_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    return json.loads(raw)


def format_context_for_prompt(
    chunks: list[Chunk],
    documents: dict[str, Document],
    metadatas: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        doc = documents[chunk.document_id]
        meta = metadatas[i - 1] if i - 1 < len(metadatas) else {}
        source = doc.filename
        if meta.get("page"):
            source += f" (第{meta['page']}页)"
        elif meta.get("heading"):
            source += f" ({meta['heading']})"
        parts.append(f"[{i}] 来源: {source}\n内容: {chunk.text.strip()}")
    return "\n\n".join(parts)

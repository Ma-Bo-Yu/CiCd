"""将理论题 Markdown 导入演示知识库。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.knowledge_base import KnowledgeBase
from app.services.documents import create_document_record, save_upload_bytes


def _resolve_files() -> list[Path]:
    settings = get_settings()
    base = settings.seed_docs_dir
    names = [n.strip() for n in settings.seed_doc_files.split(",") if n.strip()]
    paths: list[Path] = []
    for name in names:
        p = base / name
        if not p.is_file():
            raise FileNotFoundError(f"找不到种子文档: {p}")
        paths.append(p)
    return paths


def count_seed_files() -> int:
    return len(_resolve_files())


def run_theory_seed(db: Session, owner_id: str) -> dict:
    settings = get_settings()
    kb = KnowledgeBase(
        name="理论题面试知识库",
        description="复盘、面试题整理、AI 相关面试题（前后端分离版 seed）",
        owner_id=owner_id,
    )
    db.add(kb)
    db.flush()

    paths = _resolve_files()
    doc_ids: list[str] = []
    for path in paths:
        doc = create_document_record(db, kb.id, path.name)
        content = path.read_bytes()
        save_upload_bytes(doc, path.name, content)
        doc_ids.append(doc.id)

    db.commit()
    db.refresh(kb)

    return {
        "knowledge_base_id": kb.id,
        "document_ids": doc_ids,
        "files": [p.name for p in paths],
        "message": f"已创建知识库并登记 {len(doc_ids)} 个 Markdown 文档，索引任务请由调用方触发",
    }

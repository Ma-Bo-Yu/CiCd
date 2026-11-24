"""One-off smoke test for KB extractive answer order."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.db import SessionLocal
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.rag import RAGService

QUESTION = "RAG知识库 PDF 等文档是如何进行入库的？"


def main() -> None:
    with SessionLocal() as db:
        svc = RAGService(db)
        doc = db.scalars(
            select(Document).where(Document.filename.like("%面试%"))
        ).first()
        kb_id = doc.kb_id if doc else None
        if not kb_id:
            kb = db.scalars(select(KnowledgeBase)).first()
            kb_id = kb.id if kb else None
        if not kb_id:
            print("no kb")
            return
        retrieved = asyncio.run(svc.retrieve(kb_id, QUESTION))
        top = retrieved[0].chunk.chroma_id if retrieved else "none"
        print("top chunk:", top)
        ans = svc._extractive_answer(QUESTION, retrieved)
        out = ROOT / "scripts" / "_answer_out.txt"
        out.write_text(ans, encoding="utf-8")
        print("wrote", out, "len", len(ans))
        i1 = ans.find("第一")
        i3 = ans.find("第三")
        ok = i1 >= 0 and (i3 < 0 or i1 < i3)
        print("order_ok:", ok, "has 解析层:", "解析层" in ans, "has 入库层:", "入库层" in ans)
        print("html_junk:", "color:" in ans or '="' in ans)


if __name__ == "__main__":
    main()

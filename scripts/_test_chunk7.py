import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.db import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.rag import RAGService

QUESTION = "RAG知识库 PDF 等文档是如何进行入库的？"

with SessionLocal() as db:
    svc = RAGService(db)
    d = db.scalars(select(Document).where(Document.filename.like("%口语背诵%"))).first()
    c = db.scalars(select(Chunk).where(Chunk.chroma_id == f"{d.id}_7")).first()
    raw = c.text
    (ROOT / "scripts" / "_chunk7_raw.txt").write_text(raw, encoding="utf-8")
    block = svc._extract_conclusion_from_raw(QUESTION, raw)
    (ROOT / "scripts" / "_chunk7_ans.txt").write_text(block, encoding="utf-8")
    print("plausible", svc._answer_plausible(QUESTION, block))
    print("len", len(block))

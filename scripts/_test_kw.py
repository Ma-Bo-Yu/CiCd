import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.db import SessionLocal
from app.models.document import Document
from app.services.rag import RAGService

QUESTION = "RAG知识库 PDF 等文档是如何进行入库的？"

with SessionLocal() as db:
    svc = RAGService(db)
    doc = db.scalars(select(Document).where(Document.filename.like("%口语背诵%"))).first()
    kb_id = doc.kb_id
    kw = svc.retrieve_keyword(kb_id, QUESTION, top_k=5)
    print("keyword top:")
    for r in kw:
        print(r.chunk.chroma_id, r.score, r.chunk.text[:120].replace("\n", " "))
    vec = asyncio.run(svc.retrieve(kb_id, QUESTION))
    print("vector top:")
    for r in vec:
        print(r.chunk.chroma_id, r.chunk.text[:120].replace("\n", " "))

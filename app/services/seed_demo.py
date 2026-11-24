"""演示环境 seed：同一知识库内 PDF + Markdown。"""

from __future__ import annotations

import pymupdf
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.knowledge_base import KnowledgeBase
from app.services.documents import create_document_record, save_upload_bytes

SEED_MD = """# 力学基础讲义

## 牛顿第一定律

牛顿第一定律指出：一切物体在没有受到外力作用时，总保持静止状态或匀速直线运动状态。这也称为惯性定律。

惯性是物体保持原有运动状态的性质。质量越大，惯性越大。

## 应用举例

在行驶的汽车上，当司机突然刹车时，乘客身体会向前倾，这是因为乘客具有惯性，倾向于保持原来的运动状态。

## 小结

牛顿第一定律揭示了力与运动的关系：力是改变物体运动状态的原因，而不是维持运动的原因。
"""

SEED_PDF_TEXT = (
    "力学基础 PDF\n\n"
    "牛顿第一定律：一切物体在没有受到外力作用时，总保持静止或匀速直线运动状态。\n"
    "惯性：物体保持原有运动状态的性质。\n"
    "例子：汽车急刹车时乘客前倾。"
)


def _make_pdf_bytes() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), SEED_PDF_TEXT, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def run_seed(db: Session, owner_id: str) -> dict:
    settings = get_settings()
    kb = KnowledgeBase(
        name="演示知识库",
        description="含 PDF + Markdown，用于答辩黄金路径（AC-INT-01）",
        owner_id=owner_id,
    )
    db.add(kb)
    db.flush()

    doc_ids: list[str] = []

    md_doc = create_document_record(db, kb.id, "力学基础.md")
    save_upload_bytes(md_doc, "力学基础.md", SEED_MD.encode("utf-8"))
    doc_ids.append(md_doc.id)

    pdf_doc = create_document_record(db, kb.id, "力学基础.pdf")
    save_upload_bytes(pdf_doc, "力学基础.pdf", _make_pdf_bytes())
    doc_ids.append(pdf_doc.id)

    db.commit()
    db.refresh(kb)

    return {
        "knowledge_base_id": kb.id,
        "document_ids": doc_ids,
        "message": "演示知识库已创建（PDF + Markdown），索引任务请由调用方触发",
    }

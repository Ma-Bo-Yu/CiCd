"""知识库归属校验（多用户隔离）。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import ChatSession
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.research import ResearchJob
from app.models.user import User
from app.models.video import VideoJob


def load_user_kbs(db: Session, user: User) -> list[KnowledgeBase]:
    return list(
        db.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_id == user.id)
            .order_by(KnowledgeBase.created_at.desc())
        ).all()
    )


def get_owned_kb(db: Session, kb_id: str, user: User) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "知识库不存在"}},
        )
    return kb


def get_owned_document(db: Session, document_id: str, user: User) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "文档不存在"}},
        )
    get_owned_kb(db, doc.kb_id, user)
    return doc


def get_owned_session(db: Session, session_id: str, user: User) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "会话不存在"}},
        )
    get_owned_kb(db, session.kb_id, user)
    return session


def get_owned_research_job(db: Session, job_id: str, user: User) -> ResearchJob:
    job = db.get(ResearchJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "研究任务不存在"}},
        )
    get_owned_kb(db, job.kb_id, user)
    return job


def get_owned_video_job(db: Session, job_id: str, user: User) -> VideoJob:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "视频任务不存在"}},
        )
    get_owned_kb(db, job.kb_id, user)
    return job

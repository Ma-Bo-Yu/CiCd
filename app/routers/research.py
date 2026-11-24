from __future__ import annotations

import json
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.research import ResearchJob
from app.models.user import User
from app.services.auth import require_user_api
from app.services.billing import (
    KIND_DOC_UPLOAD,
    KIND_RESEARCH_CREATE,
    assert_can_create_research,
    assert_can_upload_docs,
    record_usage,
)
from app.services.documents import create_document_record, save_upload_bytes
from app.services.ownership import get_owned_kb, get_owned_research_job, load_user_kbs
from app.services.tasks import background_ingest, background_research

router = APIRouter(prefix="/api/v1/research", tags=["research"])


class ResearchJobCreate(BaseModel):
    kb_id: str
    topic: str = Field(..., min_length=1, max_length=500)


def report_filename_for_job(job: ResearchJob) -> str:
    safe_topic = re.sub(r'[\\/:*?"<>|]+', "_", job.topic)[:80]
    return f"{safe_topic}_report.md"


def find_ingested_report_document(db: Session, job: ResearchJob) -> Document | None:
    filename = report_filename_for_job(job)
    return db.scalars(
        select(Document).where(
            Document.kb_id == job.kb_id,
            Document.filename == filename,
        )
    ).first()


def _job_dict(job: ResearchJob) -> dict:
    steps = json.loads(job.steps_json) if job.steps_json else []
    return {
        "id": job.id,
        "kb_id": job.kb_id,
        "topic": job.topic,
        "status": job.status,
        "steps": steps,
        "report_md": job.report_md,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def do_ingest_report(
    db: Session,
    job: ResearchJob,
    background_tasks: BackgroundTasks,
    *,
    as_api: bool = True,
    as_page: bool = False,
) -> dict:
    if not job.report_md:
        raise HTTPException(status_code=400, detail="报告尚未生成")

    existing = find_ingested_report_document(db, job)
    if existing is not None:
        return {
            "status": "already",
            "document_id": existing.id,
            "filename": existing.filename,
            "message": "已入库",
        }

    kb = db.get(KnowledgeBase, job.kb_id)
    owner = db.get(User, kb.owner_id) if kb and kb.owner_id else None
    if owner is not None:
        assert_can_upload_docs(db, owner, 1, as_api=as_api, as_page=as_page)

    filename = report_filename_for_job(job)
    doc = create_document_record(db, job.kb_id, filename)
    save_upload_bytes(doc, filename, job.report_md.encode("utf-8"))
    if owner is not None:
        record_usage(db, owner, KIND_DOC_UPLOAD, doc.id)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(background_ingest, doc.id)
    return {
        "status": "accepted",
        "document_id": doc.id,
        "filename": filename,
        "message": "已入库",
    }


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_research_job(
    body: ResearchJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    get_owned_kb(db, body.kb_id, user)
    assert_can_create_research(db, user, as_api=True)
    job = ResearchJob(kb_id=body.kb_id, topic=body.topic.strip(), status="pending")
    db.add(job)
    db.flush()
    record_usage(db, user, KIND_RESEARCH_CREATE, job.id)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(background_research, job.id)
    return _job_dict(job)


@router.get("/jobs")
def list_research_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> list[dict]:
    kb_ids = [k.id for k in load_user_kbs(db, user)]
    if not kb_ids:
        return []
    jobs = db.scalars(
        select(ResearchJob)
        .where(ResearchJob.kb_id.in_(kb_ids))
        .order_by(ResearchJob.created_at.desc())
    ).all()
    return [_job_dict(j) for j in jobs]


@router.get("/jobs/{job_id}")
def get_research_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    job = get_owned_research_job(db, job_id, user)
    return _job_dict(job)


@router.post("/jobs/{job_id}/ingest", status_code=status.HTTP_202_ACCEPTED)
def ingest_report(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    job = get_owned_research_job(db, job_id, user)
    return do_ingest_report(db, job, background_tasks)

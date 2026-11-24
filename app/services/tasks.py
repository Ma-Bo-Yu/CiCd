import asyncio

from app.config import get_settings
from app.db import SessionLocal
from app.models.video import VideoJob
from app.services.agent import run_research_job
from app.services.ingest import IngestService
from app.services.video_render import render_video_from_script


def background_ingest(document_id: str) -> None:
    db = SessionLocal()
    try:
        service = IngestService(db)
        asyncio.run(service.ingest_document(document_id))
    finally:
        db.close()


def background_research(job_id: str) -> None:
    db = SessionLocal()
    try:
        asyncio.run(run_research_job(job_id, db))
    finally:
        db.close()


def run_video_render(job_id: str, script_md: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(VideoJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.error_message = None
        db.commit()
        try:
            output = asyncio.run(render_video_from_script(script_md, job_id))
            settings = get_settings()
            data_root = settings.data_dir.resolve()
            job.output_video_path = str(output.resolve().relative_to(data_root))
            job.status = "succeeded"
            job.error_message = None
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
        db.commit()
    finally:
        db.close()

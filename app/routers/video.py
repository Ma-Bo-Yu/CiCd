from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.user import User
from app.models.video import VideoJob
from app.services.auth import require_user_api
from app.services.billing import KIND_VIDEO_CREATE, assert_can_create_video, record_usage
from app.services.citations import citations_from_json, citations_to_json
from app.services.ownership import get_owned_kb, get_owned_video_job, load_user_kbs
from app.services.tasks import run_video_render
from app.services.video_script import VideoScriptService

router = APIRouter(prefix="/api/v1/video", tags=["video"])


class VideoJobCreate(BaseModel):
    kb_id: str
    topic: str = Field(..., min_length=1, max_length=500)
    target_minutes: int = Field(3, ge=1, le=8)


class VideoJobRead(BaseModel):
    id: str
    kb_id: str
    topic: str
    target_minutes: int
    status: str
    script_md: str | None
    script_confirmed: bool
    citations: list[dict] | None = None
    output_video_path: str | None
    error_message: str | None
    created_at: object
    updated_at: object

    model_config = {"from_attributes": True}


class ScriptPatch(BaseModel):
    script_md: str


def _job_read(job: VideoJob) -> dict:
    return {
        "id": job.id,
        "kb_id": job.kb_id,
        "topic": job.topic,
        "target_minutes": job.target_minutes,
        "status": job.status,
        "script_md": job.script_md,
        "script_confirmed": job.script_confirmed,
        "citations": citations_from_json(job.citations_json) or None,
        "output_video_path": job.output_video_path,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.post("/jobs", response_model=VideoJobRead, status_code=status.HTTP_201_CREATED)
async def create_video_job(
    body: VideoJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    get_owned_kb(db, body.kb_id, user)
    assert_can_create_video(db, user, as_api=True)
    if body.target_minutes not in (3, 5, 8):
        body.target_minutes = 3

    svc = VideoScriptService(db)
    script_md, citations = await svc.generate(body.kb_id, body.topic, body.target_minutes)

    job = VideoJob(
        kb_id=body.kb_id,
        topic=body.topic.strip(),
        target_minutes=body.target_minutes,
        status="draft",
        script_md=script_md,
        script_confirmed=False,
        citations_json=citations_to_json(citations) if citations else None,
    )
    db.add(job)
    db.flush()
    record_usage(db, user, KIND_VIDEO_CREATE, job.id)
    db.commit()
    db.refresh(job)
    return _job_read(job)


@router.get("/jobs", response_model=list[VideoJobRead])
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> list[dict]:
    kb_ids = [k.id for k in load_user_kbs(db, user)]
    if not kb_ids:
        return []
    jobs = db.scalars(
        select(VideoJob)
        .where(VideoJob.kb_id.in_(kb_ids))
        .order_by(VideoJob.created_at.desc())
    ).all()
    return [_job_read(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=VideoJobRead)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    job = get_owned_video_job(db, job_id, user)
    return _job_read(job)


@router.patch("/jobs/{job_id}/script", response_model=VideoJobRead)
def patch_script(
    job_id: str,
    body: ScriptPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    job = get_owned_video_job(db, job_id, user)
    job.script_md = body.script_md
    db.commit()
    db.refresh(job)
    return _job_read(job)


class ConfirmRequest(BaseModel):
    script_confirmed: bool = False


@router.post("/jobs/{job_id}/confirm", response_model=VideoJobRead)
def confirm_job(
    job_id: str,
    body: ConfirmRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    job = get_owned_video_job(db, job_id, user)
    if not body.script_confirmed:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "not_confirmed", "message": "请先确认讲稿"}},
        )
    if not job.script_md:
        raise HTTPException(status_code=400, detail="讲稿为空")
    if job.status in ("pending", "running"):
        return _job_read(job)

    job.script_confirmed = True
    job.status = "pending"
    job.error_message = None
    db.commit()
    background_tasks.add_task(run_video_render, job.id, job.script_md)
    db.refresh(job)
    return _job_read(job)


@router.get("/jobs/{job_id}/download")
def download_video(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
):
    job = get_owned_video_job(db, job_id, user)
    if job.status != "succeeded" or not job.output_video_path:
        raise HTTPException(status_code=404, detail="视频不可用")
    settings = get_settings()
    path = settings.data_dir / job.output_video_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")

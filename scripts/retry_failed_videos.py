"""将失败/卡住的视频任务重置为可再次渲染，并可选立即重试。"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.db import SessionLocal
from app.models.video import VideoJob
from app.services.tasks import run_video_render
from sqlalchemy import select


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="重置后立即后台渲染")
    args = parser.parse_args()

    with SessionLocal() as db:
        jobs = db.scalars(
            select(VideoJob)
            .where(VideoJob.status.in_(("failed", "running", "error")))
            .order_by(VideoJob.updated_at.desc())
        ).all()
        if not jobs:
            jobs = db.scalars(select(VideoJob).order_by(VideoJob.updated_at.desc()).limit(5)).all()

        for job in jobs:
            print(f"{job.id} | {job.topic} | status={job.status}")
            if job.error_message:
                print(f"  err: {job.error_message[:200]}")

        failed = [j for j in jobs if j.error_message or j.status in ("failed", "error")]
        if not failed:
            print("没有带错误的任务；可在页面直接点「确认并渲染」。")
            return

        job = failed[0]
        print(f"\n重置任务: {job.id}")
        job.status = "script_ready"
        job.error_message = None
        db.commit()
        script = job.script_md or ""
        if args.run and script.strip():
            print("开始渲染…")
            run_video_render(job.id, script)
            db.refresh(job)
            print(f"完成 status={job.status} error={job.error_message}")
        else:
            print("已重置。请打开视频详情页勾选并点击「确认并渲染」，或加 --run 自动渲染。")


if __name__ == "__main__":
    main()

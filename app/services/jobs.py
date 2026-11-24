"""Job 状态辅助（Research / Video 共用，PRD §12）。"""

from sqlalchemy.orm import Session


def set_job_error(db: Session, job, message: str, status: str = "failed") -> None:
    job.status = status
    job.error_message = message
    db.commit()

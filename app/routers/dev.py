from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.services.auth import require_user_api
from app.services.billing import (
    KIND_DOC_UPLOAD,
    KIND_KB_CREATE,
    assert_can_create_kb,
    assert_can_upload_docs,
    record_usage,
)
from app.services.seed_theory import count_seed_files, run_theory_seed
from app.services.tasks import background_ingest

router = APIRouter(prefix="/api/v1/dev", tags=["dev"])


@router.post("/seed")
def seed_demo(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    n_files = count_seed_files()
    assert_can_create_kb(db, user, as_api=True)
    assert_can_upload_docs(db, user, n_files, as_api=True)
    result = run_theory_seed(db, owner_id=user.id)
    record_usage(db, user, KIND_KB_CREATE, result["knowledge_base_id"])
    for doc_id in result["document_ids"]:
        record_usage(db, user, KIND_DOC_UPLOAD, doc_id)
        background_tasks.add_task(background_ingest, doc_id)
    db.commit()
    out = {
        "knowledge_base_id": result["knowledge_base_id"],
        "document_id": result["document_ids"][0] if result["document_ids"] else None,
        "files": result["files"],
        "message": "理论题 Markdown 已导入，向量索引任务已启动",
    }
    return out

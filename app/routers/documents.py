from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.services.auth import require_user_api
from app.services.document_lifecycle import delete_document
from app.services.ownership import get_owned_document
from app.services.tasks import background_ingest

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> None:
    get_owned_document(db, document_id, user)
    delete_document(db, document_id)


@router.post("/{document_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict[str, str]:
    doc = get_owned_document(db, document_id, user)
    background_tasks.add_task(background_ingest, doc.id)
    return {"status": "accepted", "document_id": document_id}

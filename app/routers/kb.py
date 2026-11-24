from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.document import DocumentRead
from app.schemas.kb import KnowledgeBaseCreate, KnowledgeBaseRead
from app.services.auth import require_user_api
from app.services.billing import (
    KIND_DOC_UPLOAD,
    KIND_KB_CREATE,
    assert_can_create_kb,
    assert_can_upload_docs,
    record_usage,
)
from app.services.chroma_store import delete_kb_collection
from app.services.documents import create_document_record, save_upload
from app.services.ownership import get_owned_kb, load_user_kbs
from app.services.tasks import background_ingest

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


def _doc_count(db: Session, kb_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(Document).where(Document.kb_id == kb_id)
    ) or 0


def _kb_to_read(kb: KnowledgeBase, db: Session) -> KnowledgeBaseRead:
    return KnowledgeBaseRead(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        document_count=_doc_count(db, kb.id),
    )


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> list[KnowledgeBaseRead]:
    rows = load_user_kbs(db, user)
    return [_kb_to_read(kb, db) for kb in rows]


@router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    body: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> KnowledgeBaseRead:
    assert_can_create_kb(db, user, as_api=True)
    kb = KnowledgeBase(
        name=body.name.strip(),
        description=body.description,
        owner_id=user.id,
    )
    db.add(kb)
    db.flush()
    record_usage(db, user, KIND_KB_CREATE, kb.id)
    db.commit()
    db.refresh(kb)
    return _kb_to_read(kb, db)


@router.get("/{kb_id}", response_model=KnowledgeBaseRead)
def get_knowledge_base(
    kb_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> KnowledgeBaseRead:
    kb = get_owned_kb(db, kb_id, user)
    return _kb_to_read(kb, db)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    kb_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> None:
    kb = get_owned_kb(db, kb_id, user)
    delete_kb_collection(kb_id)
    db.delete(kb)
    db.commit()


@router.get("/{kb_id}/documents", response_model=list[DocumentRead])
def list_documents(
    kb_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> list[DocumentRead]:
    get_owned_kb(db, kb_id, user)
    docs = db.scalars(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    ).all()
    return [DocumentRead.model_validate(d) for d in docs]


@router.post("/{kb_id}/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> DocumentRead:
    get_owned_kb(db, kb_id, user)
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    assert_can_upload_docs(db, user, 1, as_api=True)
    try:
        doc = create_document_record(db, kb_id, file.filename)
        content = await file.read()
        save_upload(doc, file, content=content)
        record_usage(db, user, KIND_DOC_UPLOAD, doc.id)
        db.commit()
        db.refresh(doc)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(background_ingest, doc.id)
    return DocumentRead.model_validate(doc)

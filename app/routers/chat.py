from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.chat import ChatSession, Message, SessionMode
from app.models.user import User
from app.services.auth import require_user_api
from app.services.citations import citations_from_json, citations_to_json
from app.services.chat_history import trim_history
from app.services.chat_stream import stream_session_message, streaming_sse_response
from app.services.llm import LLMService
from app.services.ownership import get_owned_kb, get_owned_session, load_user_kbs
from app.services.rag import RAGService
from app.services.vision import VisionService, normalize_vision_question

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class SessionCreate(BaseModel):
    kb_id: str
    mode: str = SessionMode.CHAT_QA.value


class SessionRead(BaseModel):
    id: str
    kb_id: str
    mode: str
    title: str
    created_at: object

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict] | None = None
    created_at: object

    model_config = {"from_attributes": True}


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(
    body: SessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> ChatSession:
    get_owned_kb(db, body.kb_id, user)
    session = ChatSession(kb_id=body.kb_id, mode=body.mode, title="新对话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(
    kb_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> list[ChatSession]:
    owned_ids = {k.id for k in load_user_kbs(db, user)}
    if not owned_ids:
        return []
    stmt = select(ChatSession).order_by(ChatSession.created_at.desc())
    if kb_id:
        get_owned_kb(db, kb_id, user)
        stmt = stmt.where(ChatSession.kb_id == kb_id)
    else:
        stmt = stmt.where(ChatSession.kb_id.in_(owned_ids))
    return list(db.scalars(stmt).all())


@router.get("/sessions/{session_id}/messages", response_model=list[MessageRead])
def list_messages(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> list[dict]:
    get_owned_session(db, session_id, user)
    rows = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    ).all()
    out: list[dict] = []
    for m in rows:
        out.append(
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "citations": citations_from_json(m.citations_json) or None,
                "created_at": m.created_at,
            }
        )
    return out


@router.post("/sessions/{session_id}/messages", response_model=MessageRead)
async def post_message(
    session_id: str,
    body: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    session = get_owned_session(db, session_id, user)

    history_rows = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(10)
    ).all()
    history_rows.reverse()
    history = trim_history(
        [{"role": m.role, "content": m.content} for m in history_rows]
    )

    user_msg = Message(session_id=session_id, role="user", content=body.content.strip())
    db.add(user_msg)
    if session.title == "新对话":
        session.title = body.content.strip()[:40]
    db.commit()

    text = body.content.strip()
    citations: list[dict] | None = None

    if session.mode == SessionMode.CHAT_AI.value:
        llm = LLMService()
        msgs: list[dict] = [
            {
                "role": "system",
                "content": "你是通用 AI 学习助手，用中文清晰回答，可适当举例。",
            }
        ]
        for msg in history:
            msgs.append({"role": msg["role"], "content": msg["content"]})
        msgs.append({"role": "user", "content": text})
        answer = await llm.chat_completion(msgs)
    else:
        rag = RAGService(db)
        answer, citations = await rag.answer(
            session.kb_id, text, history=history, kb_strict=True
        )

    assistant = Message(
        session_id=session_id,
        role="assistant",
        content=answer,
        citations_json=citations_to_json(citations) if citations else None,
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)

    return {
        "id": assistant.id,
        "role": assistant.role,
        "content": assistant.content,
        "citations": citations or None,
        "created_at": assistant.created_at,
    }


@router.post("/sessions/{session_id}/messages/stream")
async def post_message_stream(
    session_id: str,
    body: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
):
    session = get_owned_session(db, session_id, user)
    text = body.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")
    return streaming_sse_response(stream_session_message(session, text, db))


@router.post("/sessions/{session_id}/messages/vision", response_model=MessageRead)
async def post_vision_message(
    session_id: str,
    content: str = Form(""),
    image: UploadFile = File(...),
    mode: str = Form("vision_rag"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user_api),
) -> dict:
    session = get_owned_session(db, session_id, user)
    if session.mode != SessionMode.CHAT_VISION.value:
        session.mode = SessionMode.CHAT_VISION.value

    question = normalize_vision_question(content, mode)

    settings = get_settings()
    img_dir = settings.data_dir / "images" / session_id
    img_dir.mkdir(parents=True, exist_ok=True)
    safe = Path(image.filename or "upload.png").name
    img_path = img_dir / safe
    raw = await image.read()
    if len(raw) > settings.max_image_bytes:
        raise HTTPException(status_code=400, detail="图片过大（最大 10MB）")
    img_path.write_bytes(raw)

    user_msg = Message(
        session_id=session_id,
        role="user",
        content=question,
        image_path=str(img_path.relative_to(settings.data_dir)),
    )
    db.add(user_msg)
    if session.title == "新对话":
        session.title = question[:40] or "图像对话"
    db.commit()

    try:
        vision = VisionService(db)
        answer, citations_json = await vision.answer(
            session.kb_id, question, img_path, mode=mode
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    assistant = Message(
        session_id=session_id,
        role="assistant",
        content=answer,
        citations_json=citations_json,
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)

    return {
        "id": assistant.id,
        "role": assistant.role,
        "content": assistant.content,
        "citations": citations_from_json(assistant.citations_json) or None,
        "created_at": assistant.created_at,
    }

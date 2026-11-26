from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.chat import ChatSession, Message, SessionMode
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.research import ResearchJob
from app.models.user import User
from app.models.video import VideoJob
from app.config import get_settings
from app.services.auth import require_user
from app.services.billing import (
    KIND_DOC_UPLOAD,
    KIND_KB_CREATE,
    KIND_RESEARCH_CREATE,
    KIND_VIDEO_CREATE,
    PLAN_LIMITS,
    PLAN_LABELS,
    PRO_DAYS,
    PRO_PRICE_CNY,
    assert_can_create_kb,
    assert_can_create_research,
    assert_can_create_video,
    assert_can_upload_docs,
    downgrade_to_free,
    record_usage,
    usage_snapshot,
)
from app.services.ownership import (
    get_owned_kb,
    get_owned_research_job,
    get_owned_session,
    get_owned_video_job,
    load_user_kbs,
)
from app.services.chroma_store import delete_kb_collection
from app.services.citations import citations_from_json, citations_to_json
from app.services.text_utils import strip_html
from app.services.documents import create_document_record, save_upload
from app.services.chat_history import trim_history
from app.services.document_lifecycle import delete_document
from app.services.chat_stream import stream_session_message, streaming_sse_response
from app.services.vision_stream import stream_vision_message
from app.services.llm import LLMService
from app.services.rag import RAGService
from app.services.tasks import background_ingest, background_research, run_video_render
from app.services.vision import VisionService, normalize_vision_question
from app.services.video_script import VideoScriptService

router = APIRouter(tags=["pages"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


async def _assistant_reply(
    session: ChatSession,
    text: str,
    history: list[dict[str, str]],
    db: Session,
) -> tuple[str, list[dict] | None]:
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
        return await llm.chat_completion(msgs), None

    rag = RAGService(db)
    answer, citations = await rag.answer(
        session.kb_id, text, history=history, kb_strict=True
    )
    return answer, citations


_SESSION_TITLE_PLACEHOLDERS = frozenset({"新对话", "AI 对话", "图像对话"})


def _truncate_session_label(text: str, max_len: int = 40) -> str:
    t = " ".join((text or "").split())
    if not t:
        return "新对话"
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _session_sidebar_labels(db: Session, sessions: list[ChatSession]) -> dict[str, str]:
    if not sessions:
        return {}
    ids = [s.id for s in sessions]
    first_user: dict[str, str] = {}
    for msg in db.scalars(
        select(Message)
        .where(Message.session_id.in_(ids), Message.role == "user")
        .order_by(Message.created_at.asc())
    ).all():
        if msg.session_id not in first_user:
            first_user[msg.session_id] = msg.content

    labels: dict[str, str] = {}
    for s in sessions:
        if s.title and s.title not in _SESSION_TITLE_PLACEHOLDERS:
            labels[s.id] = _truncate_session_label(s.title)
        elif s.id in first_user:
            labels[s.id] = _truncate_session_label(first_user[s.id])
        else:
            labels[s.id] = (
                "新对话"
                if s.title in _SESSION_TITLE_PLACEHOLDERS
                else (s.title or "新对话")
            )
    return labels


def _message_view(messages: list[Message]) -> list[dict]:
    return [
        {
            "role": m.role,
            "content": m.content,
            "citations": citations_from_json(m.citations_json),
            "image_url": f"/media/{m.image_path}" if m.image_path else None,
        }
        for m in messages
    ]


def _doc_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Document.kb_id, func.count()).group_by(Document.kb_id)
    ).all()
    return {kb_id: count for kb_id, count in rows}


def _load_kbs(db: Session, user: User) -> list[KnowledgeBase]:
    return load_user_kbs(db, user)


def _user_kb_ids(db: Session, user: User) -> list[str]:
    return [k.id for k in _load_kbs(db, user)]


def _render(request: Request, name: str, user: User, **context):
    context = {"current_user": user, **context}
    return templates.TemplateResponse(request=request, name=name, context=context)


_NAV_LINKS: list[tuple[str, str]] = [
    ("/", "首页"),
    ("/kb", "知识库"),
    ("/chat", "知识库问答"),
    ("/chat/ai", "AI 对话"),
    ("/research", "研究"),
    ("/video", "视频"),
    ("/billing", "套餐"),
    ("/settings", "设置"),
]


def _is_nav_active(href: str, path: str) -> bool:
    if href == "/":
        return path == "/"
    if href == "/chat":
        if path.startswith("/chat/ai") or path.startswith("/chat/vision"):
            return False
        return path == "/chat" or path.startswith("/chat/")
    return path == href or path.startswith(href + "/")


def _nav_items(path: str) -> list[dict[str, str | bool]]:
    return [
        {"href": href, "label": label, "active": _is_nav_active(href, path)}
        for href, label in _NAV_LINKS
    ]


templates.env.globals["nav_items_for_path"] = _nav_items


def _prepare_video_citations(citations: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for c in citations:
        key = str(c.get("chunk_id") or c.get("document_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        excerpt = strip_html(str(c.get("excerpt") or ""))
        if len(excerpt) > 200:
            excerpt = excerpt[:200] + "…"
        item = dict(c)
        item["excerpt"] = excerpt
        out.append(item)
        if len(out) >= 8:
            break
    return out


def _resolve_kb_id(
    request: Request, db: Session, user: User, query_kb_id: str | None = None
) -> str | None:
    kbs = _load_kbs(db, user)
    if not kbs:
        return None
    ids = {k.id for k in kbs}
    if query_kb_id and query_kb_id in ids:
        return query_kb_id
    cookie = request.cookies.get("current_kb_id")
    if cookie and cookie in ids:
        return cookie
    return kbs[0].id


def _ai_chat_page(
    request: Request,
    db: Session,
    user: User,
    kb_id: str | None,
    session_id: str | None,
):
    kbs = _load_kbs(db, user)
    if not kbs:
        return _render(
            request,
            "chat/ai_vision.html",
            user,
            page_title="AI 对话",
            knowledge_bases=[],
            kb_id=None,
            sessions=[],
            session_labels={},
            current_session=None,
            messages=[],
        )
    kb_id = _resolve_kb_id(request, db, user, kb_id) or kbs[0].id
    sessions = db.scalars(
        select(ChatSession)
        .where(
            ChatSession.kb_id == kb_id,
            ChatSession.mode == SessionMode.CHAT_AI.value,
        )
        .order_by(ChatSession.created_at.desc())
    ).all()
    current_session = None
    if session_id:
        try:
            current_session = get_owned_session(db, session_id, user)
        except HTTPException:
            current_session = None
    if current_session is not None and current_session.mode != SessionMode.CHAT_AI.value:
        current_session = None
    if current_session is None and sessions:
        current_session = sessions[0]
    messages: list[Message] = []
    if current_session:
        messages = list(
            db.scalars(
                select(Message)
                .where(Message.session_id == current_session.id)
                .order_by(Message.created_at.asc())
            ).all()
        )
    session_labels = _session_sidebar_labels(db, sessions)
    return _render(
        request,
        "chat/ai_vision.html",
        user,
        page_title="AI 对话",
        knowledge_bases=kbs,
        kb_id=kb_id,
        sessions=sessions,
        session_labels=session_labels,
        current_session=current_session,
        messages=_message_view(messages),
    )


@router.get("/ai")
def legacy_ai_chat_redirect():
    """旧 Vue 路由 /ai → AI 对话页。"""
    return RedirectResponse(url="/chat/ai", status_code=302)


@router.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    kb_ids = _user_kb_ids(db, user)
    recent_videos = []
    if kb_ids:
        recent_videos = list(
            db.scalars(
                select(VideoJob)
                .where(VideoJob.kb_id.in_(kb_ids))
                .order_by(VideoJob.created_at.desc())
                .limit(5)
            ).all()
        )
    kbs = _load_kbs(db, user)
    current_kb = kbs[0] if kbs else None
    return _render(
        request,
        "index.html",
        user,
        page_title="工作台首页",
        knowledge_bases=kbs,
        current_kb=current_kb,
        recent_videos=recent_videos,
    )


@router.get("/kb")
def kb_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    counts = _doc_counts(db)
    return _render(
        request,
        "kb/list.html",
        user,
        page_title="知识库",
        knowledge_bases=_load_kbs(db, user),
        doc_counts=counts,
    )


@router.post("/kb")
def kb_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    assert_can_create_kb(db, user, as_page=True)
    kb = KnowledgeBase(
        name=name, description=description.strip() or None, owner_id=user.id
    )
    db.add(kb)
    db.flush()
    record_usage(db, user, KIND_KB_CREATE, kb.id)
    db.commit()
    counts = _doc_counts(db)
    if request.headers.get("HX-Request"):
        return _render(
            request,
            "kb/partials/table.html",
            user,
            knowledge_bases=_load_kbs(db, user),
            doc_counts=counts,
        )
    return RedirectResponse(url="/kb", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/kb/{kb_id}")
def kb_detail(
    kb_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    kb = get_owned_kb(db, kb_id, user)
    documents = db.scalars(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    ).all()
    return _render(
        request,
        "kb/detail.html",
        user,
        page_title=kb.name,
        kb=kb,
        documents=documents,
    )


@router.post("/kb/{kb_id}/upload")
async def kb_upload(
    kb_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    kb = get_owned_kb(db, kb_id, user)
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    assert_can_upload_docs(db, user, 1, as_page=True)
    try:
        content = await file.read()
        settings = get_settings()
        max_upload = settings.max_image_bytes * 2
        if len(content) > max_upload:
            raise HTTPException(status_code=400, detail="文件过大（上限约 20MB）")
        doc = create_document_record(db, kb_id, file.filename)
        save_upload(doc, file, content=content)
        record_usage(db, user, KIND_DOC_UPLOAD, doc.id)
        db.commit()
        db.refresh(doc)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(background_ingest, doc.id)
    documents = db.scalars(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    ).all()
    return _render(
        request,
        "kb/partials/documents.html",
        user,
        kb=kb,
        documents=documents,
    )


@router.post("/kb/{kb_id}/documents/{doc_id}/delete")
def kb_delete_doc(
    kb_id: str,
    doc_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_kb(db, kb_id, user)
    doc = db.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    delete_document(db, doc_id)
    kb = get_owned_kb(db, kb_id, user)
    documents = db.scalars(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    ).all()
    return _render(
        request,
        "kb/partials/documents.html",
        user,
        kb=kb,
        documents=documents,
    )


@router.post("/kb/{kb_id}/documents/{doc_id}/reindex")
def kb_reindex_doc(
    kb_id: str,
    doc_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_kb(db, kb_id, user)
    doc = db.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    background_tasks.add_task(background_ingest, doc.id)
    kb = get_owned_kb(db, kb_id, user)
    documents = db.scalars(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    ).all()
    return _render(
        request,
        "kb/partials/documents.html",
        user,
        kb=kb,
        documents=documents,
    )


@router.post("/kb/{kb_id}/delete")
def kb_delete(
    kb_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    kb = get_owned_kb(db, kb_id, user)
    delete_kb_collection(kb_id)
    db.delete(kb)
    db.commit()
    counts = _doc_counts(db)
    if request.headers.get("HX-Request"):
        return _render(
            request,
            "kb/partials/table.html",
            user,
            knowledge_bases=_load_kbs(db, user),
            doc_counts=counts,
        )
    return RedirectResponse(url="/kb", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/chat")
async def chat_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    kb_id: str | None = Query(None),
    session_id: str | None = Query(None),
):
    kbs = _load_kbs(db, user)
    if not kbs:
        return _render(
            request,
            "chat/index.html",
            user,
            page_title="问答",
            knowledge_bases=[],
            sessions=[],
            session_labels={},
            current_session=None,
            messages=[],
        )
    kb_id = _resolve_kb_id(request, db, user, kb_id) or kbs[0].id
    sessions = db.scalars(
        select(ChatSession)
        .where(
            ChatSession.kb_id == kb_id,
            ChatSession.mode == SessionMode.CHAT_QA.value,
        )
        .order_by(ChatSession.created_at.desc())
    ).all()
    current_session = None
    messages: list[Message] = []
    if session_id:
        try:
            current_session = get_owned_session(db, session_id, user)
        except HTTPException:
            current_session = None
    elif sessions:
        current_session = sessions[0]
    if current_session and current_session.mode != SessionMode.CHAT_QA.value:
        current_session = None
    if current_session:
        messages = list(
            db.scalars(
                select(Message)
                .where(Message.session_id == current_session.id)
                .order_by(Message.created_at.asc())
            ).all()
        )
    return _render(
        request,
        "chat/index.html",
        user,
        page_title="问答",
        knowledge_bases=kbs,
        kb_id=kb_id,
        sessions=sessions,
        session_labels=_session_sidebar_labels(db, sessions),
        current_session=current_session,
        messages=_message_view(messages),
    )


@router.get("/kb/{kb_id}/documents-fragment")
def kb_documents_fragment(
    kb_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    kb = get_owned_kb(db, kb_id, user)
    documents = db.scalars(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    ).all()
    return _render(
        request,
        "kb/partials/documents.html",
        user,
        kb=kb,
        documents=documents,
    )


@router.post("/chat/sessions")
def chat_new_session(
    kb_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_kb(db, kb_id, user)
    session = ChatSession(kb_id=kb_id, mode=SessionMode.CHAT_QA.value, title="新对话")
    db.add(session)
    db.commit()
    return RedirectResponse(
        url=f"/chat?kb_id={kb_id}&session_id={session.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/chat/sessions/{session_id}/messages")
async def chat_post_message(
    session_id: str,
    request: Request,
    content: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    session = get_owned_session(db, session_id, user)
    if session.mode != SessionMode.CHAT_QA.value:
        raise HTTPException(status_code=400, detail="请使用 AI 对话页面")
    text = content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")

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

    user_msg = Message(session_id=session_id, role="user", content=text)
    db.add(user_msg)
    if session.title == "新对话":
        session.title = text[:40]
    db.commit()

    answer, citations = await _assistant_reply(session, text, history, db)
    assistant = Message(
        session_id=session_id,
        role="assistant",
        content=answer,
        citations_json=citations_to_json(citations) if citations else None,
    )
    db.add(assistant)
    db.commit()

    messages = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    ).all()
    return _render(
        request,
        "chat/partials/messages.html",
        user,
        messages=_message_view(messages),
    )


@router.get("/chat/sessions/{session_id}/messages-fragment")
def chat_messages_fragment(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_session(db, session_id, user)
    messages = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    ).all()
    return _render(
        request,
        "chat/partials/messages.html",
        user,
        messages=_message_view(messages),
    )


@router.get("/chat/ai/sessions/{session_id}/messages-fragment")
def chat_ai_messages_fragment(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_session(db, session_id, user)
    messages = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    ).all()
    return _render(
        request,
        "chat/partials/messages.html",
        user,
        messages=_message_view(messages),
    )


@router.post("/chat/sessions/{session_id}/messages/stream")
async def chat_stream_message(
    session_id: str,
    content: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    session = get_owned_session(db, session_id, user)
    if session.mode != SessionMode.CHAT_QA.value:
        raise HTTPException(status_code=400, detail="请使用 AI 对话页面")
    text = content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")

    return streaming_sse_response(stream_session_message(session, text, db))


@router.get("/chat/ai")
async def chat_ai_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    tab: str | None = Query(None),
    kb_id: str | None = Query(None),
    session_id: str | None = Query(None),
):
    if tab == "vision":
        q = f"kb_id={kb_id}" if kb_id else ""
        if session_id:
            q = f"{q}&session_id={session_id}" if q else f"session_id={session_id}"
        url = f"/chat/ai?{q}" if q else "/chat/ai"
        return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    return _ai_chat_page(request, db, user, kb_id, session_id)


@router.post("/chat/ai/sessions")
def chat_ai_new_session(
    kb_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_kb(db, kb_id, user)
    session = ChatSession(
        kb_id=kb_id,
        mode=SessionMode.CHAT_AI.value,
        title="新对话",
    )
    db.add(session)
    db.commit()
    return RedirectResponse(
        url=f"/chat/ai?kb_id={kb_id}&session_id={session.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/chat/ai/sessions/{session_id}/messages")
async def chat_ai_post_message(
    session_id: str,
    request: Request,
    content: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    session = get_owned_session(db, session_id, user)
    if session.mode != SessionMode.CHAT_AI.value:
        raise HTTPException(status_code=400, detail="非 AI 对话会话")
    text = content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")

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

    user_msg = Message(session_id=session_id, role="user", content=text)
    db.add(user_msg)
    if session.title in ("新对话", "AI 对话"):
        session.title = text[:40]
    db.commit()

    answer, citations = await _assistant_reply(session, text, history, db)
    assistant = Message(
        session_id=session_id,
        role="assistant",
        content=answer,
        citations_json=citations_to_json(citations) if citations else None,
    )
    db.add(assistant)
    db.commit()

    messages = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    ).all()
    return _render(
        request,
        "chat/partials/messages.html",
        user,
        messages=_message_view(messages),
    )


@router.post("/chat/ai/sessions/{session_id}/messages/stream")
async def chat_ai_stream_message(
    session_id: str,
    content: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    session = get_owned_session(db, session_id, user)
    if session.mode != SessionMode.CHAT_AI.value:
        raise HTTPException(status_code=400, detail="非 AI 对话会话")
    text = content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")

    return streaming_sse_response(stream_session_message(session, text, db))


@router.get("/video")
def video_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    kb_ids = _user_kb_ids(db, user)
    jobs = []
    if kb_ids:
        jobs = list(
            db.scalars(
                select(VideoJob)
                .where(VideoJob.kb_id.in_(kb_ids))
                .order_by(VideoJob.created_at.desc())
            ).all()
        )
    kbs = _load_kbs(db, user)
    return _render(
        request,
        "video/list.html",
        user,
        page_title="讲解视频",
        jobs=jobs,
        knowledge_bases=kbs,
    )


@router.post("/video")
async def video_create(
    kb_id: str = Form(...),
    topic: str = Form(...),
    target_minutes: int = Form(3),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_kb(db, kb_id, user)
    assert_can_create_video(db, user, as_page=True)
    svc = VideoScriptService(db)
    script_md, citations = await svc.generate(kb_id, topic.strip(), target_minutes)
    job = VideoJob(
        kb_id=kb_id,
        topic=topic.strip(),
        target_minutes=target_minutes,
        status="draft",
        script_md=script_md,
        script_confirmed=False,
        citations_json=citations_to_json(citations) if citations else None,
    )
    db.add(job)
    db.flush()
    record_usage(db, user, KIND_VIDEO_CREATE, job.id)
    db.commit()
    return RedirectResponse(url=f"/video/{job.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/video/{job_id}")
def video_detail(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    job = get_owned_video_job(db, job_id, user)
    citations = _prepare_video_citations(citations_from_json(job.citations_json))
    return _render(
        request,
        "video/detail.html",
        user,
        page_title=f"视频 · {job.topic}",
        job=job,
        citations=citations,
    )


@router.post("/video/{job_id}/script")
def video_save_script(
    job_id: str,
    script_md: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    job = get_owned_video_job(db, job_id, user)
    job.script_md = script_md
    db.commit()
    return RedirectResponse(url=f"/video/{job_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/video/{job_id}/render")
def video_render(
    job_id: str,
    background_tasks: BackgroundTasks,
    script_confirmed: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    job = get_owned_video_job(db, job_id, user)
    if script_confirmed != "on":
        raise HTTPException(status_code=400, detail="请先勾选确认讲稿")
    if not job.script_md:
        raise HTTPException(status_code=400, detail="讲稿为空")
    job.script_confirmed = True
    job.status = "pending"
    job.error_message = None
    db.commit()
    background_tasks.add_task(run_video_render, job.id, job.script_md)
    return RedirectResponse(url=f"/video/{job_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/video/{job_id}/progress")
def video_progress(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    job = get_owned_video_job(db, job_id, user)
    return _render(
        request,
        "video/partials/progress.html",
        user,
        job=job,
    )


@router.get("/media/{file_path:path}")
def serve_media(file_path: str, user: User = Depends(require_user)):
    settings = get_settings()
    full = (settings.data_dir / file_path).resolve()
    root = settings.data_dir.resolve()
    if not str(full).startswith(str(root)) or not full.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(full)


@router.get("/chat/vision")
async def chat_vision_page(
    request: Request,
    kb_id: str | None = Query(None),
    session_id: str | None = Query(None),
):
    q = []
    if kb_id:
        q.append(f"kb_id={kb_id}")
    if session_id:
        q.append(f"session_id={session_id}")
    url = "/chat/ai" + ("?" + "&".join(q) if q else "")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.post("/chat/vision/sessions")
def chat_vision_new_session(
    kb_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """旧图像页入口：改为创建 AI 对话会话。"""
    return chat_ai_new_session(kb_id=kb_id, db=db, user=user)


@router.post("/chat/vision/sessions/{session_id}/messages")
async def chat_vision_post(
    session_id: str,
    request: Request,
    content: str = Form(...),
    mode: str = Form("vision_rag"),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    session = get_owned_session(db, session_id, user)
    settings = get_settings()
    img_dir = settings.data_dir / "images" / session_id
    img_dir.mkdir(parents=True, exist_ok=True)
    safe = Path(image.filename or "upload.png").name
    img_path = img_dir / safe
    raw = await image.read()
    if len(raw) > settings.max_image_bytes:
        raise HTTPException(status_code=400, detail="图片过大（最大 10MB）")
    img_path.write_bytes(raw)

    question = normalize_vision_question(content, mode)
    user_msg = Message(
        session_id=session_id,
        role="user",
        content=question,
        image_path=str(img_path.relative_to(settings.data_dir)),
    )
    db.add(user_msg)
    db.commit()

    vision = VisionService(db)
    try:
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

    messages = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    ).all()
    return _render(
        request,
        "chat/partials/messages.html",
        user,
        messages=_message_view(messages),
    )


@router.post("/chat/vision/sessions/{session_id}/messages/stream")
async def chat_vision_stream(
    session_id: str,
    content: str = Form(""),
    mode: str = Form("vision_rag"),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    session = get_owned_session(db, session_id, user)
    if session.mode not in (
        SessionMode.CHAT_VISION.value,
        SessionMode.CHAT_AI.value,
    ):
        raise HTTPException(status_code=400, detail="该会话不支持图像消息")
    text = normalize_vision_question(content, mode)

    settings = get_settings()
    img_dir = settings.data_dir / "images" / session_id
    img_dir.mkdir(parents=True, exist_ok=True)
    safe = Path(image.filename or "upload.png").name
    img_path = img_dir / safe
    raw = await image.read()
    if len(raw) > settings.max_image_bytes:
        raise HTTPException(status_code=400, detail="图片过大（最大 10MB）")
    img_path.write_bytes(raw)

    sid = session.id
    kb_id = session.kb_id

    user_msg = Message(
        session_id=session_id,
        role="user",
        content=text,
        image_path=str(img_path.relative_to(settings.data_dir)),
    )
    db.add(user_msg)
    if session.title in _SESSION_TITLE_PLACEHOLDERS:
        session.title = _truncate_session_label(text)
    db.commit()

    gen = stream_vision_message(sid, kb_id, text, img_path, mode, db)
    return streaming_sse_response(gen)


@router.post("/chat/ai/sessions/{session_id}/messages/vision/stream")
async def chat_ai_vision_stream(
    session_id: str,
    content: str = Form(""),
    mode: str = Form("vision_rag"),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """AI 对话页：同一会话内粘贴/上传图片识图。"""
    session = get_owned_session(db, session_id, user)
    if session.mode != SessionMode.CHAT_AI.value:
        raise HTTPException(status_code=400, detail="非 AI 对话会话")
    return await chat_vision_stream(session_id, content, mode, image, db, user)


@router.get("/research")
def research_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from app.routers.research import find_ingested_report_document

    kb_ids = _user_kb_ids(db, user)
    jobs = []
    if kb_ids:
        jobs = list(
            db.scalars(
                select(ResearchJob)
                .where(ResearchJob.kb_id.in_(kb_ids))
                .order_by(ResearchJob.created_at.desc())
            ).all()
        )
    job_rows = [
        {
            "job": job,
            "ingested_doc": find_ingested_report_document(db, job),
        }
        for job in jobs
    ]
    kbs = _load_kbs(db, user)
    return _render(
        request,
        "research/list.html",
        user,
        page_title="研究任务",
        job_rows=job_rows,
        knowledge_bases=kbs,
    )


@router.post("/research")
def research_create(
    background_tasks: BackgroundTasks,
    kb_id: str = Form(...),
    topic: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_kb(db, kb_id, user)
    assert_can_create_research(db, user, as_page=True)
    job = ResearchJob(kb_id=kb_id, topic=topic.strip(), status="pending")
    db.add(job)
    db.flush()
    record_usage(db, user, KIND_RESEARCH_CREATE, job.id)
    db.commit()
    background_tasks.add_task(background_research, job.id)
    return RedirectResponse(url=f"/research/{job.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/research/{job_id}")
def research_detail(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    import json

    from app.routers.research import find_ingested_report_document

    job = get_owned_research_job(db, job_id, user)
    steps = json.loads(job.steps_json) if job.steps_json else []
    ingested_doc = find_ingested_report_document(db, job)
    notice = request.query_params.get("notice")
    return _render(
        request,
        "research/detail.html",
        user,
        page_title=f"研究 · {job.topic}",
        job=job,
        steps=steps,
        ingested_doc=ingested_doc,
        notice=notice,
    )


@router.get("/research/{job_id}/panel")
def research_panel(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    import json

    from app.routers.research import find_ingested_report_document

    job = get_owned_research_job(db, job_id, user)
    steps = json.loads(job.steps_json) if job.steps_json else []
    ingested_doc = find_ingested_report_document(db, job)
    return _render(
        request,
        "research/partials/panel.html",
        user,
        job=job,
        steps=steps,
        ingested_doc=ingested_doc,
    )


@router.post("/research/{job_id}/ingest")
def research_ingest_page(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from app.routers.research import do_ingest_report

    job = get_owned_research_job(db, job_id, user)
    result = do_ingest_report(db, job, background_tasks, as_api=False, as_page=True)
    notice = "already_ingested" if result.get("status") == "already" else "ingested"
    return RedirectResponse(
        url=f"/research/{job_id}?notice={notice}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/partials/nav")
def partial_nav(
    request: Request,
    path: str = "/",
    user: User = Depends(require_user),
):
    current = path.strip() if path.strip().startswith("/") else "/"
    return _render(
        request,
        "partials/nav.html",
        user,
        nav_items=_nav_items(current),
    )


@router.post("/kb/select")
def kb_select(
    request: Request,
    kb_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    get_owned_kb(db, kb_id, user)
    referer = request.headers.get("referer") or "/"
    response = RedirectResponse(url=referer, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("current_kb_id", kb_id, max_age=60 * 60 * 24 * 30)
    return response


@router.get("/billing")
def billing_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    quota: str | None = Query(None),
):
    from app.models.payment import PaymentOrder
    from app.services.billing import QUOTA_MESSAGES

    snap = usage_snapshot(db, user)
    quota_msg = QUOTA_MESSAGES.get(quota) if quota else None
    recent_orders = list(
        db.scalars(
            select(PaymentOrder)
            .where(PaymentOrder.user_id == user.id)
            .order_by(PaymentOrder.created_at.desc())
            .limit(5)
        ).all()
    )
    return _render(
        request,
        "billing/index.html",
        user,
        page_title="套餐与用量",
        snap=snap,
        plans=PLAN_LIMITS,
        plan_labels=PLAN_LABELS,
        pro_price=PRO_PRICE_CNY,
        pro_days=PRO_DAYS,
        quota_msg=quota_msg,
        recent_orders=recent_orders,
    )


@router.post("/billing/checkout")
def billing_checkout(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """创建沙箱订单并进入收银台（对齐真实支付：先下单再支付）。"""
    from app.services.payment_sandbox import create_pro_order

    order = create_pro_order(db, user)
    db.commit()
    return RedirectResponse(
        url=f"/billing/sandbox/{order.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/billing/sandbox/{order_id}")
def billing_sandbox_checkout(
    order_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from app.services.payment_sandbox import get_order_for_user

    order = get_order_for_user(db, order_id, user)
    return _render(
        request,
        "billing/sandbox_checkout.html",
        user,
        page_title="沙箱收银台",
        order=order,
        pro_days=PRO_DAYS,
    )


@router.post("/billing/sandbox/{order_id}/pay-success")
def billing_sandbox_pay_success(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from app.services.payment_sandbox import get_order_for_user, sandbox_pay_success

    order = get_order_for_user(db, order_id, user)
    sandbox_pay_success(db, order, user)
    db.commit()
    return RedirectResponse(url="/billing?upgraded=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/billing/sandbox/{order_id}/pay-fail")
def billing_sandbox_pay_fail(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from app.services.payment_sandbox import get_order_for_user, sandbox_pay_fail

    order = get_order_for_user(db, order_id, user)
    sandbox_pay_fail(db, order, user)
    db.commit()
    return RedirectResponse(url="/billing?pay_failed=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/billing/sandbox/{order_id}/cancel")
def billing_sandbox_cancel(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from app.services.payment_sandbox import get_order_for_user, sandbox_cancel

    order = get_order_for_user(db, order_id, user)
    sandbox_cancel(db, order, user)
    db.commit()
    return RedirectResponse(
        url="/billing?pay_cancelled=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/billing/downgrade")
def billing_downgrade(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    downgrade_to_free(user)
    db.commit()
    return RedirectResponse(url="/billing?downgraded=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/settings")
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from app.services.llm import LLMService

    s = get_settings()
    llm = LLMService()
    snap = usage_snapshot(db, user)
    return _render(
        request,
        "settings.html",
        user,
        page_title="设置",
        llm_model=s.llm_model,
        embed_model=s.embed_model,
        tts_provider=s.tts_provider,
        llm_demo=llm.llm_demo,
        embed_demo=llm.embed_demo,
        snap=snap,
    )

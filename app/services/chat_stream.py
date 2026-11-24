from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import ChatSession, Message, SessionMode
from app.services.text_utils import KB_MISS_REPLY
from app.services.chat_history import trim_history
from app.services.citations import citations_to_json
from app.services.llm import LLMService
from app.services.rag import RAGService

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def streaming_sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/event-stream; charset=utf-8",
        headers=SSE_HEADERS,
    )


async def iter_answer_tokens(
    session: ChatSession,
    text: str,
    history: list[dict[str, str]],
    db: Session,
) -> AsyncIterator[tuple[str, object]]:
    llm = LLMService()
    if session.mode == SessionMode.CHAT_AI.value:
        msgs: list[dict] = [
            {
                "role": "system",
                "content": "你是通用 AI 学习助手，用中文清晰回答，可适当举例。",
            }
        ]
        for msg in history:
            msgs.append({"role": msg["role"], "content": msg["content"]})
        msgs.append({"role": "user", "content": text})
        try:
            # DeepSeek 等流式接口可能较慢，给足时间再降级离线演示
            async with asyncio.timeout(90.0):
                async for piece in llm.chat_completion_stream(
                    msgs, on_http_error="raise"
                ):
                    yield "token", piece
        except Exception:
            offline = (
                "（大模型暂不可用，以下为离线演示回答）\n\n"
                + llm._demo_chat(msgs)
            )
            step = 2
            for i in range(0, len(offline), step):
                yield "token", offline[i : i + step]
                await asyncio.sleep(0.02)
        yield "done", None
        return

    rag = RAGService(db)
    async for kind, payload in rag.iter_answer_stream(
        session.kb_id, text, history=history, kb_strict=True
    ):
        yield kind, payload


def sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_session_message(
    session: ChatSession,
    text: str,
    db: Session,
) -> AsyncIterator[str]:
    history_rows = db.scalars(
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .limit(10)
    ).all()
    history_rows.reverse()
    history = trim_history(
        [{"role": m.role, "content": m.content} for m in history_rows]
    )

    user_msg = Message(session_id=session.id, role="user", content=text)
    db.add(user_msg)
    if session.title in ("新对话", "AI 对话", "图像对话") or not session.title:
        session.title = text[:40]
    db.commit()

    full_answer = ""
    citations: list[dict] | None = None
    assistant_saved = False

    def _default_answer() -> str:
        if session.mode != SessionMode.CHAT_AI.value:
            return KB_MISS_REPLY
        return "未收到模型回复，请稍后再试。"

    def _save_assistant() -> None:
        nonlocal assistant_saved, full_answer
        if assistant_saved:
            return
        body = full_answer.strip() or _default_answer()
        if not full_answer.strip():
            full_answer = body
        assistant = Message(
            session_id=session.id,
            role="assistant",
            content=body,
            citations_json=citations_to_json(citations) if citations else None,
        )
        db.add(assistant)
        db.commit()
        assistant_saved = True

    try:
        yield sse_event({"type": "start"})

        try:
            async for kind, payload in iter_answer_tokens(session, text, history, db):
                if kind == "token":
                    full_answer += str(payload)
                    yield sse_event({"type": "token", "content": payload})
                elif kind == "done":
                    if isinstance(payload, list):
                        citations = payload
        except Exception:
            if session.mode != SessionMode.CHAT_AI.value:
                rag = RAGService(db)
                async for kind, payload in rag.iter_extractive_stream(
                    session.kb_id, text
                ):
                    if kind == "token":
                        full_answer += str(payload)
                        yield sse_event({"type": "token", "content": payload})
                    elif kind == "done" and isinstance(payload, list):
                        citations = payload
            else:
                friendly = "大模型暂时不可用，请稍后再试。"
                full_answer = friendly
                yield sse_event({"type": "token", "content": friendly})

        if not full_answer.strip():
            full_answer = _default_answer()
            yield sse_event({"type": "token", "content": full_answer})

        _save_assistant()
        cite_names = [c.get("document_name", "") for c in (citations or [])]
        yield sse_event({"type": "done", "citations": cite_names})
    finally:
        try:
            _save_assistant()
        except Exception:
            db.rollback()

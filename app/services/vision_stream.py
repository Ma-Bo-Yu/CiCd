from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.chat import Message
from app.services.chat_stream import sse_event
from app.services.citations import citations_to_json
from app.services.vision import VisionService


async def stream_vision_message(
    session_id: str,
    kb_id: str,
    content: str,
    image_path: Path,
    mode: str,
    db: Session,
) -> AsyncIterator[str]:
    vision = VisionService(db)
    full_answer = ""
    citations: list[dict] | None = None
    assistant_saved = False

    def _save_assistant() -> None:
        nonlocal assistant_saved
        if assistant_saved or not full_answer.strip():
            return
        assistant = Message(
            session_id=session_id,
            role="assistant",
            content=full_answer,
            citations_json=citations_to_json(citations) if citations else None,
        )
        db.add(assistant)
        db.commit()
        assistant_saved = True

    try:
        yield sse_event({"type": "start"})

        try:
            async for kind, payload in vision.iter_answer_stream(
                kb_id, content, image_path, mode=mode
            ):
                if kind == "token":
                    full_answer += str(payload)
                    yield sse_event({"type": "token", "content": payload})
                elif kind == "done" and isinstance(payload, list):
                    citations = payload
        except Exception as exc:
            yield sse_event({"type": "error", "message": str(exc)})
            return

        _save_assistant()
        cite_names = [c.get("document_name", "") for c in (citations or [])]
        yield sse_event({"type": "done", "citations": cite_names})
    finally:
        try:
            _save_assistant()
        except Exception:
            db.rollback()

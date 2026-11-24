from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.citations import build_citation, citations_to_json, format_context_for_prompt
from app.services.llm import LLMService
from app.services.rag import RAGService

DEFAULT_VISION_ONLY_QUESTION = "请详细描述并解读这张图片中的内容。"
DEFAULT_VISION_RAG_QUESTION = "请结合知识库资料，回答与这张图片相关的问题。"


def normalize_vision_question(content: str, mode: str) -> str:
    text = (content or "").strip()
    if text:
        return text
    if mode == "vision_only":
        return DEFAULT_VISION_ONLY_QUESTION
    return DEFAULT_VISION_RAG_QUESTION


class VisionService:
    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.llm = llm or LLMService()
        self.rag = RAGService(db, self.llm)
        self.settings = get_settings()

    def _image_data_url(self, image_path: Path) -> str:
        mime = "image/png"
        if image_path.suffix.lower() in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif image_path.suffix.lower() == ".webp":
            mime = "image/webp"
        b64 = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    async def _build_vision_prompt(
        self,
        kb_id: str,
        question: str,
        data_url: str,
        mode: str,
    ) -> tuple[str, list[dict]]:
        text_part = question
        cites: list[dict] = []

        if mode == "vision_rag":
            desc = await self.llm.chat_completion(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请用一句中文描述这张图片的主要内容。"},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                model=self.settings.vision_model,
            )
            retrieved = await self.rag.retrieve(kb_id, f"{question}\n{desc}", top_k=5)
            if retrieved:
                chunks = [r.chunk for r in retrieved]
                docs = {r.document.id: r.document for r in retrieved}
                metas = [r.metadata for r in retrieved]
                context = format_context_for_prompt(chunks, docs, metas)
                cites = [
                    build_citation(r.chunk, r.document, r.metadata) for r in retrieved
                ]
                text_part = (
                    f"用户问题：{question}\n\n参考资料：\n{context}\n\n请结合图片与参考资料用中文回答。"
                )
            else:
                text_part = (
                    f"用户问题：{question}\n\n（知识库无相关参考资料，请主要根据图片回答。）"
                )
        return text_part, cites

    async def iter_answer_stream(
        self,
        kb_id: str,
        question: str,
        image_path: Path,
        mode: str = "vision_rag",
    ) -> AsyncIterator[tuple[str, object]]:
        data_url = self._image_data_url(image_path)
        text_part, cites = await self._build_vision_prompt(
            kb_id, question, data_url, mode
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text_part},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        async for piece in self.llm.chat_completion_stream(
            messages, model=self.settings.vision_model
        ):
            yield "token", piece
        yield "done", cites

    async def answer(
        self,
        kb_id: str,
        question: str,
        image_path: Path,
        mode: str = "vision_rag",
    ) -> tuple[str, str | None]:
        """Returns (answer, citations_json or None)."""
        full = ""
        cites: list[dict] = []
        async for kind, payload in self.iter_answer_stream(
            kb_id, question, image_path, mode=mode
        ):
            if kind == "token":
                full += str(payload)
            elif kind == "done" and isinstance(payload, list):
                cites = payload
        citations_json = citations_to_json(cites) if cites else None
        return full, citations_json

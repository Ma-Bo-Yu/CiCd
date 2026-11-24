from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.llm import LLMService
from app.services.rag import RAGService


SCRIPT_PROMPT = """你是一位教学讲稿撰稿人。根据以下知识库参考资料，为主题「{topic}」撰写约 {minutes} 分钟的讲解 Markdown 讲稿。

结构要求（使用 Markdown 标题）：
# 引入
## 要点一
## 要点二
## 例子
# 小结

语言：中文，口语化，适合录制成讲解视频。不要编造参考资料中没有的内容。

参考资料：
{context}
"""

FUN_SCRIPT_PROMPT = """你是一位擅长做「趣味讲解短视频」的撰稿人。根据参考资料，为主题「{topic}」写约 {minutes} 分钟的 Markdown 讲稿。

风格：轻松、有画面感，可适度用比喻和小故事，适合配音 + 彩色动效画面（不要写成满屏大字 PPT）。
结构：
# 开场钩子
## 要点一
## 要点二
## 小例子
# 一句话总结

语言：中文口语。不要编造参考资料中没有的事实。

参考资料：
{context}
"""


class VideoScriptService:
    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.rag = RAGService(db, llm)
        self.llm = llm or LLMService()

    async def generate(self, kb_id: str, topic: str, target_minutes: int) -> tuple[str, list[dict]]:
        retrieved = await self.rag.retrieve(kb_id, topic, top_k=8)
        if retrieved:
            from app.services.citations import build_citation, format_context_for_prompt

            chunks = [r.chunk for r in retrieved]
            docs = {r.document.id: r.document for r in retrieved}
            metas = [r.metadata for r in retrieved]
            context = format_context_for_prompt(chunks, docs, metas)
            citations = [
                build_citation(r.chunk, r.document, r.metadata) for r in retrieved
            ]
        else:
            context = "（无匹配参考资料）"
            citations = []

        tpl = FUN_SCRIPT_PROMPT if get_settings().video_fun_test else SCRIPT_PROMPT
        prompt = tpl.format(topic=topic, minutes=target_minutes, context=context)
        script_md = await self.llm.chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        return script_md, citations

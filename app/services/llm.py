from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator

import httpx

from app.config import get_settings
from app.services.api_keys import is_configured_api_key

_MOCK_EMBED_DIM = 384


def _mock_embedding(text: str, dim: int = _MOCK_EMBED_DIM) -> list[float]:
    vec: list[float] = []
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    for i in range(dim):
        b = digest[i % len(digest)]
        vec.append((b / 127.5) - 1.0)
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def embed_demo(self) -> bool:
        return not is_configured_api_key(self.settings.embed_api_key)

    @property
    def llm_demo(self) -> bool:
        return not is_configured_api_key(self.settings.llm_api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.embed_demo:
            return [_mock_embedding(t) for t in texts]

        settings = self.settings
        url = f"{settings.embed_base_url.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {settings.embed_api_key}"}
        payload = {"model": settings.embed_model, "input": texts}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                return [_mock_embedding(t) for t in texts]
            data = resp.json()
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    async def chat_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        if self.llm_demo:
            return self._demo_chat(messages)

        settings = self.settings
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        payload: dict = {
            "model": model or settings.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                detail = resp.text[:300]
                raise RuntimeError(
                    f"LLM 调用失败（{resp.status_code}）。请检查 .env 中 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY。{detail}"
                )
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _stream_text_chunks(self, text: str) -> AsyncIterator[str]:
        step = 2
        for i in range(0, len(text), step):
            yield text[i : i + step]
            await asyncio.sleep(0.028)

    def _llm_user_friendly_error(self, status_code: int, body: str) -> str:
        low = body.lower()
        if status_code == 503 or "service_unavailable" in low or "too busy" in low:
            return (
                "大模型服务暂时繁忙（503），请过几分钟再试。"
                "若持续失败，可在 .env 更换 LLM 服务商或检查 API 余额。"
            )
        if status_code in (401, 403):
            return "大模型 API Key 无效或无权访问，请检查 .env 中的 LLM_API_KEY。"
        if status_code == 429:
            return "大模型请求过于频繁（429），请稍后再试。"
        return (
            f"大模型调用失败（HTTP {status_code}）。请检查 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY。"
        )

    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        *,
        on_http_error: str = "stream_message",
    ) -> AsyncIterator[str]:
        """on_http_error: stream_message=把错误当正文流出；raise=抛异常供 RAG 等降级。"""
        if self.llm_demo:
            full = self._demo_chat(messages)
            async for piece in self._stream_text_chunks(full):
                yield piece
            return

        settings = self.settings
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        payload: dict = {
            "model": model or settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        timeout = httpx.Timeout(90.0, connect=15.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="replace")[
                            :400
                        ]
                        msg = self._llm_user_friendly_error(resp.status_code, body)
                        if on_http_error == "raise":
                            raise RuntimeError(msg)
                        async for piece in self._stream_text_chunks(msg):
                            yield piece
                        return
                    got_token = False
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            got_token = True
                            yield content
                    if not got_token:
                        msg = "大模型未返回流式内容。"
                        if on_http_error == "raise":
                            raise RuntimeError(msg)
                        async for piece in self._stream_text_chunks(msg):
                            yield piece
        except httpx.TimeoutException:
            msg = "连接大模型超时，请检查网络或稍后再试。"
            if on_http_error == "raise":
                raise RuntimeError(msg) from None
            async for piece in self._stream_text_chunks(msg):
                yield piece
        except httpx.HTTPError as exc:
            msg = f"无法连接大模型服务：{exc}"
            if on_http_error == "raise":
                raise RuntimeError(msg) from None
            async for piece in self._stream_text_chunks(msg):
                yield piece

    def _demo_chat(self, messages: list[dict]) -> str:
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        if isinstance(user, list):
            user = "图像相关问题"
        user = str(user).strip()
        if user.lower() in ("你好", "hello", "hi", "在吗", "您好"):
            return "你好！我是 AI 学习助手，可以帮你解释概念、润色面试回答等。有什么想问的？"
        if "子问题" in user or "列出" in user and "子问题" in user:
            return (
                "牛顿第一定律的定义是什么？\n"
                "惯性概念如何理解？\n"
                "生活中有哪些惯性现象？"
            )
        if "JSON" in user and "tool" in user:
            if "finish" in user.lower() or "完成" in user:
                return json.dumps({"tool": "finish", "args": {}}, ensure_ascii=False)
            if "search_kb" in user:
                q = user.split("主题")[-1][:40] if "主题" in user else "牛顿第一定律"
                return json.dumps(
                    {"tool": "search_kb", "args": {"query": q.strip(), "top_k": 5}},
                    ensure_ascii=False,
                )
            return json.dumps(
                {"tool": "write_section", "args": {"title": "要点", "content": "演示模式：基于知识库片段生成的章节摘要。"}},
                ensure_ascii=False,
            )
        if "讲稿" in user or "引入" in user:
            return (
                "# 引入\n\n本节介绍牛顿第一定律与惯性。\n\n"
                "## 要点一\n\n物体在无外力时保持原运动状态。\n\n"
                "## 要点二\n\n质量越大，惯性越大。\n\n"
                "## 例子\n\n刹车时乘客前倾是惯性表现。\n\n"
                "# 小结\n\n力改变运动状态，而非维持运动。"
            )
        if "摘要" in user and "章节" in user:
            return "本报告汇总了牛顿第一定律的定义、惯性概念及生活实例。"
        if "章节内容" in user or "子问题" in user:
            return (
                "根据参考资料，牛顿第一定律描述物体在无合外力时保持静止或匀速直线运动。"
                "该规律也称惯性定律，是经典力学的基础之一。"
            )
        if "知识库" in user or "参考资料" in user:
            if "未找到" in user or "（无匹配" in user:
                return "知识库中未找到相关信息。"
            return (
                "根据知识库资料：牛顿第一定律指出，一切物体在没有受到外力作用时，"
                "总保持静止或匀速直线运动状态。这体现了物体的惯性。"
            )
        if "描述这张图片" in user:
            return "图片似乎与力学或物理示意图相关。"
        return (
            "当前未配置有效的 LLM API Key，且该问题无法走内置模板回答。"
            "请先在知识库问答中依赖检索摘录，或在 .env 填写真实 LLM_API_KEY。"
        )


def parse_agent_action(raw: str) -> dict | None:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None
    return None


def get_llm_service() -> LLMService:
    return LLMService()

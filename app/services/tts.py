from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from app.config import get_settings
from app.services.api_keys import is_configured_api_key
from app.services.text_utils import is_speakable_text, markdown_to_speech


class TTSService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        provider = self.settings.tts_provider.lower().strip()
        if provider == "dashscope":
            await self._dashscope_tts(text, output_path, voice)
        elif provider == "openai" and is_configured_api_key(self.settings.llm_api_key):
            await self._openai_tts(text, output_path)
        else:
            await self._edge_tts(text, output_path, voice or "zh-CN-XiaoxiaoNeural")

    async def _dashscope_tts(
        self, text: str, output_path: Path, voice: str | None
    ) -> None:
        key = self.settings.dashscope_api_key
        if not is_configured_api_key(key):
            raise RuntimeError(
                "未配置 DASHSCOPE_API_KEY。请在 .env 填写百炼/通义 sk-ws- 密钥，并设置 TTS_PROVIDER=dashscope。"
            )

        def _run() -> bytes:
            import dashscope
            from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

            dashscope.api_key = key
            model = self.settings.dashscope_tts_model
            voice_id = voice or self.settings.dashscope_tts_voice
            synthesizer = SpeechSynthesizer(
                model=model,
                voice=voice_id,
                format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
            )
            chunk = markdown_to_speech(text)
            if not is_speakable_text(chunk):
                raise ValueError(
                    "配音文本无效（百炼 TTS 要求可读中文/英文，不能仅为符号、分隔线或标点）。"
                    f"原文片段：{text[:120]!r}"
                )
            if len(chunk) > 500:
                chunk = chunk[:500]
            audio = synthesizer.call(chunk)
            if not audio:
                raise RuntimeError("DashScope 语音合成未返回音频")
            return audio

        data = await asyncio.to_thread(_run)
        output_path.write_bytes(data)

    async def _edge_tts(self, text: str, output_path: Path, voice: str) -> None:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))

    async def _openai_tts(self, text: str, output_path: Path) -> None:
        settings = self.settings
        url = f"{settings.llm_base_url.rstrip('/')}/audio/speech"
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        payload = {"model": "tts-1", "input": text, "voice": "alloy"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)


def get_tts_service() -> TTSService:
    return TTSService()

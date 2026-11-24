"""验证讲稿切分 + 百炼 TTS（不跑完整 FFmpeg）。"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.services.slides import split_script_to_slides
from app.services.tts import TTSService

SAMPLE = """# 装饰器应用场景
装饰器常见核心场景：**鉴权**、**日志**、**重试**、**限流**、**缓存**。
---
1. 鉴权：在视图函数执行前检查用户权限。
2. 日志：记录函数调用与耗时。
使用 `functools.wraps` 保留原函数元信息。
"""


async def main() -> None:
    slides = split_script_to_slides(SAMPLE)
    print(f"slides: {len(slides)}")
    for i, s in enumerate(slides):
        print(f"  [{i}] {s['body'][:70]}...")
    if not slides:
        print("FAIL: no slides")
        sys.exit(1)
    tts = TTSService()
    out = ROOT / "data" / "videos" / "_tts_verify" / "test.mp3"
    for i, s in enumerate(slides[:3]):
        p = out.parent / f"seg_{i}.mp3"
        await tts.synthesize(s["body"], p)
        print(f"OK TTS seg {i} -> {p.stat().st_size} bytes")
    print("ALL OK")


if __name__ == "__main__":
    asyncio.run(main())

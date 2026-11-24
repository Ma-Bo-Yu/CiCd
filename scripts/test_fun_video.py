"""本地生成一条趣味测试视频（需 FFmpeg + TTS 可用）。"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.services.video_render import render_video_from_script

SAMPLE = """# 开场钩子
## 今天玩点不一样的
向量检索就像给每段知识贴 GPS，问问题时先找最近的几条线索。
## 小例子
你问「PDF 怎么入库」，系统不会瞎编，而是去知识库里捞最相关的片段。
# 一句话总结
听懂了吗？下一集我们讲混合检索。
"""


async def main() -> None:
    settings = get_settings()
    print("VIDEO_FUN_TEST =", settings.video_fun_test)
    job_id = f"fun-test-{uuid.uuid4().hex[:8]}"
    out = await render_video_from_script(SAMPLE, job_id)
    print("OK:", out)
    print("Open:", out.resolve())


if __name__ == "__main__":
    asyncio.run(main())

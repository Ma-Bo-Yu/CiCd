import re


def markdown_to_speech(text: str) -> str:
    """把讲稿 Markdown 片段转为适合 TTS 的纯文本（百炼等接口不接受仅符号/分隔线）。"""
    t = text.strip()
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_speakable_text(text: str) -> bool:
    t = markdown_to_speech(text)
    if len(t) < 2:
        return False
    if re.fullmatch(r"[-*_#`~\s。！？!?,.，、；;：:]+", t):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z0-9]", t))


def strip_html(text: str) -> str:
    """单行摘要用：去标签并压成一行。"""
    return plain_text_from_chunk(text, single_line=True)


def plain_text_from_chunk(text: str, *, single_line: bool = False) -> str:
    """知识库摘录：去掉 HTML/Markdown 标记，保留段落结构。"""
    t = text or ""
    # 切片边界导致的残片，如 ="color:#2E7D32"> 或 style="...">
    t = re.sub(r'(?:style|class)\s*=\s*"[^"]*"\s*>', "", t, flags=re.I)
    t = re.sub(r'="\s*[^"]*"\s*>', "", t)
    t = re.sub(r"<\s*/?\s*span[^>]*>", "", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"必考\s*>\s*", "", t)
    t = re.sub(r"必考\s*", "", t)
    t = re.sub(r"\*\*\s*>\s*<\s*span[^>]*", "", t, flags=re.I)
    t = re.sub(r">\s*<\s*span[^>]*", "", t, flags=re.I)
    t = re.sub(r"^>\s?", "", t, flags=re.MULTILINE)
    t = re.sub(r"```[\s\S]*?```", "\n", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"<span[^>]*>", "", t, flags=re.I)
    if single_line:
        t = re.sub(r"\s+", " ", t)
        return t.strip()
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n[ \t]+", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


KB_MISS_REPLY = (
    "知识库中未找到与您问题相关的内容，此处不会编造答案。\n"
    "请前往「AI 对话」页面提问：http://127.0.0.1:8000/chat/ai"
)

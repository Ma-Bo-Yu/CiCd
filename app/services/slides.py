from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.text_utils import is_speakable_text, markdown_to_speech

_HR_LINE = re.compile(r"^[-*_]{3,}\s*$")


def split_script_to_slides(script_md: str) -> list[dict[str, str]]:
    """Split markdown script into slide title + body segments."""
    lines = [ln.strip() for ln in script_md.splitlines() if ln.strip()]
    slides: list[dict[str, str]] = []
    current_title = "讲解"
    buf: list[str] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        body = "\n".join(buf)
        for part in re.split(r"(?<=[。！？!?])\s*", body):
            part = part.strip()
            if part and is_speakable_text(part):
                slides.append({"title": current_title, "body": markdown_to_speech(part)})
        buf = []

    for line in lines:
        if _HR_LINE.match(line):
            continue
        if line.startswith("#"):
            flush()
            current_title = line.lstrip("#").strip() or "讲解"
        else:
            buf.append(line)
    flush()

    if not slides and script_md.strip():
        body = markdown_to_speech(script_md)[:500]
        if is_speakable_text(body):
            slides.append({"title": "讲解", "body": body})
    return slides


def render_slide(title: str, body: str, output_path: Path, size: tuple[int, int] = (1280, 720)) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype("msyh.ttc", 36)
        body_font = ImageFont.truetype("msyh.ttc", 24)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    tw = draw.textlength(title, font=title_font)
    draw.text(((size[0] - tw) / 2, 40), title, fill="black", font=title_font)

    y = 140
    for line in body.splitlines():
        draw.text((80, y), f"• {line}" if not line.startswith("•") else line, fill="#222", font=body_font)
        y += 36
    img.save(output_path)

"""趣味视频：固定场景——卡通小马人指向黑板讲解（旁白仍走 TTS）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_WALL = (214, 226, 240)
_FLOOR = (196, 208, 220)
_BOARD_FRAME = (139, 90, 43)
_BOARD_FACE = (32, 58, 46)
_CHALK = (245, 245, 235)
_PONY_COAT = (250, 210, 160)
_PONY_MANE = (110, 62, 38)
_PONY_SHIRT = (59, 130, 246)


def _load_fonts() -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, ...]:
    try:
        board_title = ImageFont.truetype("msyhbd.ttc", 36)
        board_body = ImageFont.truetype("msyh.ttc", 24)
        badge = ImageFont.truetype("msyh.ttc", 20)
    except OSError:
        board_title = board_body = badge = ImageFont.load_default()
    return board_title, board_body, badge


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: float, max_lines: int) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines: list[str] = []
    cur = ""
    for ch in text:
        trial = cur + ch
        if measure.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and len("".join(lines)) < len(text):
        lines[-1] = lines[-1][:-1] + "…" if lines[-1] else "…"
    return lines


def _draw_classroom_bg(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    draw.rectangle((0, 0, w, h), fill=_WALL)
    draw.rectangle((0, int(h * 0.82), w, h), fill=_FLOOR)
    draw.line((0, int(h * 0.82), w, int(h * 0.82)), fill=(180, 190, 200), width=2)


def _draw_blackboard(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    body_lines: list[str],
    title_font: ImageFont.ImageFont,
    body_font: ImageFont.ImageFont,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=8, fill=_BOARD_FRAME)
    inner = (x0 + 14, y0 + 14, x1 - 14, y1 - 14)
    draw.rounded_rectangle(inner, radius=4, fill=_BOARD_FACE)
    ix0, iy0, ix1, _ = inner
    pad = 28
    y = iy0 + pad
    display_title = title if len(title) <= 22 else title[:21] + "…"
    draw.text((ix0 + pad, y), display_title, fill=_CHALK, font=title_font)
    y += int(title_font.size * 1.55)
    draw.line((ix0 + pad, y, ix1 - pad, y), fill=(200, 200, 190), width=2)
    y += 18
    for line in body_lines:
        draw.text((ix0 + pad, y), line, fill=_CHALK, font=body_font)
        y += int(body_font.size * 1.45)


def _draw_pony_teacher(draw: ImageDraw.ImageDraw, board_left: int, h: int) -> None:
    """左侧卡通小马人，手指向黑板。"""
    cx, cy = 200, int(h * 0.52)
    # 身体
    draw.rounded_rectangle(
        (cx - 55, cy + 20, cx + 55, cy + 165),
        radius=28,
        fill=_PONY_SHIRT,
    )
    draw.rounded_rectangle(
        (cx - 48, cy + 155, cx + 48, cy + 230),
        radius=20,
        fill=(60, 65, 75),
    )
    # 头
    draw.ellipse((cx - 62, cy - 75, cx + 62, cy + 55), fill=_PONY_COAT)
    draw.ellipse((cx + 18, cy - 5, cx + 58, cy + 28), fill=_PONY_COAT)
    draw.ellipse((cx + 38, cy + 8, cx + 52, cy + 22), fill=(240, 200, 200))
    # 鬃毛
    draw.pieslice((cx - 70, cy - 90, cx + 20, cy + 10), 200, 340, fill=_PONY_MANE)
    draw.ellipse((cx - 78, cy - 55, cx - 48, cy - 15), fill=_PONY_MANE)
    # 耳
    draw.polygon(
        [(cx - 58, cy - 55), (cx - 38, cy - 95), (cx - 18, cy - 50)],
        fill=_PONY_COAT,
    )
    draw.polygon(
        [(cx + 8, cy - 55), (cx + 28, cy - 92), (cx + 48, cy - 48)],
        fill=_PONY_COAT,
    )
    # 眼
    draw.ellipse((cx - 28, cy - 18, cx - 8, cy + 2), fill=(255, 255, 255))
    draw.ellipse((cx + 8, cy - 18, cx + 28, cy + 2), fill=(255, 255, 255))
    draw.ellipse((cx - 20, cy - 10, cx - 12, cy - 2), fill=(30, 30, 30))
    draw.ellipse((cx + 16, cy - 10, cx + 24, cy - 2), fill=(30, 30, 30))
    # 指向黑板的手臂
    arm_y = cy + 45
    draw.rounded_rectangle(
        (cx + 40, arm_y - 12, board_left - 30, arm_y + 12),
        radius=10,
        fill=_PONY_COAT,
    )
    draw.ellipse((board_left - 48, arm_y - 18, board_left - 12, arm_y + 18), fill=_PONY_COAT)
    # 手指
    draw.line(
        (board_left - 20, arm_y, board_left - 8, arm_y - 6),
        fill=(240, 200, 200),
        width=4,
    )
    draw.line(
        (board_left - 20, arm_y, board_left - 6, arm_y),
        fill=(240, 200, 200),
        width=4,
    )
    draw.line(
        (board_left - 20, arm_y, board_left - 8, arm_y + 6),
        fill=(240, 200, 200),
        width=4,
    )


def render_fun_slide(
    title: str,
    body: str,
    output_path: Path,
    slide_index: int = 0,
    size: tuple[int, int] = (1280, 720),
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    img = Image.new("RGB", size, _WALL)
    draw = ImageDraw.Draw(img)
    title_font, body_font, badge_font = _load_fonts()

    _draw_classroom_bg(draw, w, h)

    board = (380, 56, w - 48, h - 72)
    body_lines = _wrap_text(body, body_font, max_width=(board[2] - board[0] - 80), max_lines=4)
    _draw_blackboard(draw, board, title, body_lines, title_font, body_font)
    _draw_pony_teacher(draw, board[0], h)

    badge = "小马老师 · 黑板讲解"
    bw = draw.textlength(badge, font=badge_font)
    draw.rounded_rectangle(
        (24, 20, 24 + bw + 24, 52),
        radius=12,
        fill=(255, 255, 255),
        outline=(203, 213, 225),
    )
    draw.text((36, 26), badge, fill=(51, 65, 85), font=badge_font)

    img.save(output_path)

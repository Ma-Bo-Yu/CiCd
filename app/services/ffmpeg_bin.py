from __future__ import annotations

import shutil
import sys
from pathlib import Path

from app.config import get_settings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _exe_name(base: str) -> str:
    return f"{base}.exe" if sys.platform == "win32" else base


def _pair_in_dir(directory: Path) -> tuple[str, str] | None:
    ffmpeg = directory / _exe_name("ffmpeg")
    ffprobe = directory / _exe_name("ffprobe")
    if ffmpeg.is_file() and ffprobe.is_file():
        return str(ffmpeg), str(ffprobe)
    return None


def resolve_ffmpeg_bins() -> tuple[str, str]:
    """系统 PATH → .env FFMPEG_BIN_DIR → 项目 tools/ffmpeg/bin。"""
    settings = get_settings()
    if settings.ffmpeg_bin_dir.strip():
        found = _pair_in_dir(Path(settings.ffmpeg_bin_dir.strip()))
        if found:
            return found
        raise RuntimeError(
            f"FFMPEG_BIN_DIR 指向的目录无效：{settings.ffmpeg_bin_dir}，"
            f"需包含 {_exe_name('ffmpeg')} 与 {_exe_name('ffprobe')}。"
        )

    for name in ("ffmpeg", "ffprobe"):
        if shutil.which(name) is None:
            break
    else:
        return "ffmpeg", "ffprobe"

    for rel in (
        _PROJECT_ROOT / "tools" / "ffmpeg" / "bin",
        _PROJECT_ROOT / "ffmpeg" / "bin",
    ):
        found = _pair_in_dir(rel)
        if found:
            return found

    hint = _PROJECT_ROOT / "tools" / "ffmpeg" / "bin"
    raise RuntimeError(
        "未找到 ffmpeg/ffprobe。任选其一：\n"
        "1) 安装到系统 PATH；\n"
        f"2) 解压 FFmpeg 到项目目录，使 {hint} 下有 ffmpeg.exe 与 ffprobe.exe；\n"
        "3) 在 .env 设置 FFMPEG_BIN_DIR=上述 bin 的完整路径。\n"
        "下载：https://www.gyan.dev/ffmpeg/builds/ （ffmpeg-release-essentials.zip）"
    )

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.config import get_settings
from app.services.ffmpeg_bin import resolve_ffmpeg_bins
from app.services.slides import render_slide, split_script_to_slides
from app.services.slides_fun import render_fun_slide
from app.services.tts import TTSService


def _format_srt_time(seconds: float) -> str:
    ms = int(seconds * 1000)
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _run_ffmpeg(ffmpeg: str, args: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(
        [ffmpeg, *args],
        capture_output=True,
        cwd=str(cwd) if cwd else None,
    )
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace")
        tail = err.strip()[-1500:] if err.strip() else f"exit {result.returncode}"
        raise RuntimeError(f"ffmpeg 执行失败：{tail}")


def _audio_duration(path: Path, ffprobe: str) -> float:
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def _concat_line(media: Path) -> str:
    """concat 列表中的路径相对 concat.txt 所在目录，只能用文件名或绝对路径。"""
    name = media.name.replace("'", "'\\''")
    return f"file '{name}'"


def _segment_encode_args(
    slide_path: Path,
    audio_path: Path,
    seg_video: Path,
    dur: float,
    *,
    fun_mode: bool,
) -> list[str]:
    out = str(seg_video.resolve())
    head = [
        "-y",
        "-loop",
        "1",
        "-i",
        str(slide_path.resolve()),
        "-i",
        str(audio_path.resolve()),
    ]
    tail = [
        "-c:v",
        "libx264",
        "-t",
        str(dur),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        out,
    ]
    if fun_mode:
        frames = max(int(dur * 25), 30)
        vf = (
            f"zoompan=z='min(zoom+0.0012,1.08)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps=25,"
            "format=yuv420p"
        )
        return [*head, "-vf", vf, *tail]
    return [*head, *tail]


async def render_video_from_script(script_md: str, job_id: str) -> Path:
    ffmpeg, ffprobe = resolve_ffmpeg_bins()
    settings = get_settings()
    fun_mode = settings.video_fun_test
    work = (settings.data_dir / "videos" / job_id).resolve()
    work.mkdir(parents=True, exist_ok=True)
    slides_data = split_script_to_slides(script_md)
    if not slides_data:
        raise ValueError("讲稿为空，无法渲染")

    tts = TTSService()
    slide_paths: list[Path] = []
    audio_paths: list[Path] = []
    durations: list[float] = []
    subtitles: list[tuple[float, float, str]] = []
    cursor = 0.0

    for i, slide in enumerate(slides_data):
        text = slide["body"]
        audio_path = work / f"audio_{i:03d}.mp3"
        slide_path = work / f"slide_{i:03d}.png"
        await tts.synthesize(text, audio_path)
        if fun_mode:
            render_fun_slide(slide["title"], text, slide_path, slide_index=i)
        else:
            render_slide(slide["title"], text, slide_path)
        dur = _audio_duration(audio_path, ffprobe)
        slide_paths.append(slide_path)
        audio_paths.append(audio_path)
        durations.append(dur)
        subtitles.append((cursor, cursor + dur, text))
        cursor += dur

    srt_path = work / "subtitles.srt"
    with srt_path.open("w", encoding="utf-8") as f:
        for idx, (start, end, text) in enumerate(subtitles, start=1):
            f.write(f"{idx}\n")
            f.write(f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n")
            f.write(re.sub(r"\s+", " ", text) + "\n\n")

    concat_list = work / "concat.txt"
    with concat_list.open("w", encoding="utf-8") as f:
        for slide_path, audio_path, dur in zip(slide_paths, audio_paths, durations):
            seg_video = work / f"seg_{slide_path.stem}.mp4"
            try:
                _run_ffmpeg(
                    ffmpeg,
                    _segment_encode_args(
                        slide_path,
                        audio_path,
                        seg_video,
                        dur,
                        fun_mode=fun_mode,
                    ),
                )
            except RuntimeError:
                if not fun_mode:
                    raise
                _run_ffmpeg(
                    ffmpeg,
                    _segment_encode_args(
                        slide_path,
                        audio_path,
                        seg_video,
                        dur,
                        fun_mode=False,
                    ),
                )
            f.write(_concat_line(seg_video) + "\n")

    merged = work / "merged.mp4"
    _run_ffmpeg(
        ffmpeg,
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "concat.txt",
            "-c",
            "copy",
            "merged.mp4",
        ],
        cwd=work,
    )

    output = (settings.data_dir / "videos" / f"{job_id}.mp4").resolve()
    if fun_mode:
        _run_ffmpeg(
            ffmpeg,
            ["-y", "-i", str(merged.resolve()), "-c", "copy", str(output)],
            cwd=work,
        )
    else:
        try:
            _run_ffmpeg(
                ffmpeg,
                [
                    "-y",
                    "-i",
                    str(merged.resolve()),
                    "-vf",
                    "subtitles=subtitles.srt",
                    "-c:a",
                    "copy",
                    str(output),
                ],
                cwd=work,
            )
        except RuntimeError:
            _run_ffmpeg(
                ffmpeg,
                ["-y", "-i", str(merged.resolve()), "-c", "copy", str(output)],
                cwd=work,
            )

    return output

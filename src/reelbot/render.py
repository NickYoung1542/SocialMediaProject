from __future__ import annotations

import random
import subprocess
from pathlib import Path

from .config import ROOT
from .footage import Media

W, H, FPS = 1080, 1920, 30


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        cwd=cwd, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-800:]}")


def render_segment(media: Media, duration: float, dest: Path) -> None:
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    run_ffmpeg([
        "-stream_loop", "-1", "-i", str(media.path), "-vf", vf,
        "-t", f"{duration:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS), str(dest),
    ])


def _concat_list(paths: list[Path], dest: Path) -> None:
    dest.write_text("".join(f"file '{p.name}'\n" for p in paths), encoding="utf-8")


def pick_music() -> Path | None:
    tracks = [p for p in (ROOT / "assets" / "music").glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a"}]
    return random.choice(tracks) if tracks else None


def assemble(workdir: Path, segments: list[Path], voices: list[Path], captions: Path, out: Path) -> None:
    _concat_list(segments, workdir / "segments.txt")
    _concat_list(voices, workdir / "voices.txt")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", "segments.txt", "-c", "copy", "video_raw.mp4"], cwd=workdir)
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", "voices.txt", "-c:a", "aac", "-b:a", "192k", "narration.m4a"], cwd=workdir)

    music = pick_music()
    sub = f"ass={captions.name}"
    if music:
        run_ffmpeg(
            ["-i", "video_raw.mp4", "-i", "narration.m4a", "-stream_loop", "-1", "-i", str(music),
             "-filter_complex",
             f"[0:v]{sub}[v];[2:a]volume=0.10[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "[v]", "-map", "[a]", "-shortest", "-c:v", "libx264", "-preset", "medium",
             "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out)],
            cwd=workdir,
        )
    else:
        run_ffmpeg(
            ["-i", "video_raw.mp4", "-i", "narration.m4a", "-vf", sub, "-map", "0:v", "-map", "1:a",
             "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
            cwd=workdir,
        )

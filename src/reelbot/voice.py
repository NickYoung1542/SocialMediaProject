from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from .config import Account


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class SceneAudio:
    path: Path
    start: float
    duration: float
    words: list[Word]


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


async def _synth(text: str, account: Account, path: Path) -> list[Word]:
    comm = edge_tts.Communicate(
        text, account.voice, rate=account.rate, pitch=account.pitch, boundary="WordBoundary"
    )
    words: list[Word] = []
    with open(path, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                words.append(Word(chunk["text"], start, start + chunk["duration"] / 10_000_000))
    return words


def synthesize_scenes(texts: list[str], account: Account, workdir: Path) -> list[SceneAudio]:
    results: list[SceneAudio] = []
    cursor = 0.0
    for i, text in enumerate(texts):
        path = workdir / f"voice_{i:02d}.mp3"
        for attempt in range(3):
            try:
                words = asyncio.run(_synth(text, account, path))
                break
            except Exception:
                if attempt == 2:
                    raise
        duration = probe_duration(path)
        shifted = [Word(w.text, w.start + cursor, w.end + cursor) for w in words]
        results.append(SceneAudio(path, cursor, duration, shifted))
        cursor += duration
    return results

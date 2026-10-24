from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import topics
from .captions import build_ass
from .config import Account, out_dir
from .footage import find_media
from .render import assemble, render_segment
from .research import fetch_source
from .script import ScriptRejected, write_script
from .voice import probe_duration, synthesize_scenes


@dataclass
class Result:
    status: str  # "ready" or "held"
    folder: Path
    reason: str = ""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def generate(account: Account, animal: str | None = None, log=print) -> Result:
    conn = topics.connect()
    animal, angle = topics.pick_topic(conn, account.name, animal)
    folder = out_dir() / f"{datetime.now():%Y%m%d-%H%M%S}_{_slug(animal)}"
    folder.mkdir(parents=True)
    log(f"Topic: {animal} / {angle}")

    title, source = fetch_source(animal)
    log(f"Source: Wikipedia '{title}' ({len(source)} chars)")

    try:
        script = write_script(account, animal, angle, source)
    except ScriptRejected as exc:
        topics.record(conn, account.name, animal, angle, "held", str(folder))
        (folder / "meta.json").write_text(json.dumps({"status": "held", "reason": str(exc)}, indent=2))
        return Result("held", folder, f"script failed fact-check: {exc}")
    log(f"Script: {script.word_count} words, {len(script.scenes)} scenes")

    audio = synthesize_scenes([s.text for s in script.scenes], account, folder)
    total = audio[-1].start + audio[-1].duration
    log(f"Voiceover: {total:.1f}s")

    used: set[str] = set()
    segments: list[Path] = []
    for i, (scene, clip) in enumerate(zip(script.scenes, audio)):
        media = find_media(scene.query, animal, used)
        if media is None:
            raise RuntimeError(f"No footage for scene {i} ({scene.query!r}); check PEXELS_API_KEY / PIXABAY_API_KEY")
        seg = folder / f"seg_{i:02d}.mp4"
        render_segment(media, clip.duration, seg)
        segments.append(seg)
        log(f"  scene {i + 1}/{len(script.scenes)}: {media.source_id}")

    build_ass([w for a in audio for w in a.words], folder / "captions.ass")
    final = folder / "video.mp4"
    assemble(folder, segments, [a.path for a in audio], folder / "captions.ass", final)
    duration = probe_duration(final)
    log(f"Rendered {final.name}: {duration:.1f}s")

    reasons = []
    if not account.min_seconds <= duration <= account.max_seconds:
        reasons.append(f"duration {duration:.0f}s outside {account.min_seconds}-{account.max_seconds}s")
    status = "held" if reasons else "ready"

    meta = {
        "status": status,
        "reason": "; ".join(reasons),
        "animal": animal,
        "angle": angle,
        "title": script.title,
        "caption": f"{script.caption} {' '.join(script.hashtags)}".strip(),
        "duration": round(duration, 1),
        "source": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        "ai_generated": True,
        "narration": script.narration,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    topics.record(conn, account.name, animal, angle, status, str(folder))
    for leftover in [*folder.glob("seg_*.mp4"), *folder.glob("voice_*.mp3"), *folder.glob("*.txt"), folder / "video_raw.mp4", folder / "narration.m4a"]:
        leftover.unlink(missing_ok=True)
    return Result(status, folder, meta["reason"])

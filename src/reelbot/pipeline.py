from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import topics
from .captions import build_ass
from .config import Account, out_dir
from .footage import clip_pool
from .render import assemble, render_segment
from .research import fetch_source
from .script import ScriptRejected, write_script
from .voice import probe_duration, synthesize_scenes

MIN_CLIPS = 8
SHOT_SECONDS = 3.2


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

    base_pool = clip_pool(animal, [])
    log(f"Footage: {len(base_pool)} matching clips for {animal}")
    if len(base_pool) < MIN_CLIPS:
        reason = f"only {len(base_pool)} matching clips for {animal} (need {MIN_CLIPS})"
        topics.record(conn, account.name, animal, angle, "held", str(folder))
        (folder / "meta.json").write_text(json.dumps({"status": "held", "reason": reason}, indent=2))
        return Result("held", folder, reason)

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

    pool = clip_pool(animal, [s.query for s in script.scenes])
    used: set[str] = set()
    segments: list[Path] = []
    shot = 0
    for i, (scene, clip) in enumerate(zip(script.scenes, audio)):
        scene_clips = clip_pool(animal, [scene.query], limit=10, generic=False)
        n_shots = max(1, round(clip.duration / SHOT_SECONDS))
        shot_len = clip.duration / n_shots
        for _ in range(n_shots):
            choice = next((c for c in scene_clips + pool if c.source_id not in used), None)
            reused = choice is None
            if reused:
                used.clear()
                choice = scene_clips[0] if scene_clips else pool[0]
            used.add(choice.source_id)
            media = choice.fetch()
            seg = folder / f"seg_{shot:02d}.mp4"
            render_segment(media, shot_len, seg, start=random.uniform(0, 3) if reused else 0.0)
            segments.append(seg)
            shot += 1
        log(f"  scene {i + 1}/{len(script.scenes)}: {n_shots} shots")

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

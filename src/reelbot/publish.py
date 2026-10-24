from __future__ import annotations

import json
from pathlib import Path

from . import tiktok, topics
from .config import Account


def post_next(account: Account, log=print) -> bool:
    """Post the oldest ready video. Returns True if one was posted."""
    conn = topics.connect()
    queued = topics.next_ready(conn, account.name)
    if queued is None:
        log("No ready videos to post.")
        return False
    video_id, folder = queued
    folder_path = Path(folder)
    meta_path = folder_path / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    log(f"Posting {meta['animal']} ({meta['angle']}) from {folder_path.name}")
    status = tiktok.publish(account, folder_path / "video.mp4", meta["caption"], log)
    meta.update({"status": "posted", "tiktok_status": status})
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    topics.set_status(conn, video_id, "posted")
    if account.tiktok_mode == "draft":
        log("Open TikTok > Inbox/notifications to review and tap Post. Caption is in meta.json.")
    return True


def daily(account: Account, max_attempts: int = 3, log=print) -> int:
    """Generate a fresh video (retrying held ones with other topics), then post it."""
    from .pipeline import generate

    # Post any backlog first so a failed earlier upload is not skipped.
    conn = topics.connect()
    if topics.next_ready(conn, account.name) is None:
        for attempt in range(1, max_attempts + 1):
            try:
                result = generate(account, log=log)
            except Exception as exc:  # noqa: BLE001 - one bad topic must not stop the daily run
                log(f"Attempt {attempt} failed: {exc}")
                continue
            if result.status == "ready":
                break
            log(f"Attempt {attempt} held: {result.reason}")
        else:
            log("No video passed checks today.")
            return 2
    try:
        post_next(account, log)
    except tiktok.TikTokError as exc:
        log(f"Posting failed (video stays queued for the next run): {exc}")
        return 3
    return 0

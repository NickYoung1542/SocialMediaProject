from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import cache_dir, env

PEXELS_URL = "https://api.pexels.com/videos/search"
PIXABAY_URL = "https://pixabay.com/api/videos/"


@dataclass
class Media:
    path: Path
    source_id: str


def _download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(1 << 16):
                fh.write(chunk)
    return dest


def _pexels(query: str, used: set[str]) -> Media | None:
    key = env("PEXELS_API_KEY")
    if not key:
        return None
    resp = requests.get(
        PEXELS_URL,
        headers={"Authorization": key},
        params={"query": query, "orientation": "portrait", "per_page": 15, "size": "medium"},
        timeout=30,
    )
    if resp.status_code != 200:
        return None
    videos = [v for v in resp.json().get("videos", []) if f"pexels:{v['id']}" not in used and v["duration"] >= 4]
    random.shuffle(videos)
    for video in videos:
        files = [f for f in video["video_files"] if f["file_type"] == "video/mp4" and (f.get("height") or 0) >= 1080]
        if not files:
            continue
        best = min(files, key=lambda f: f["height"])
        dest = cache_dir() / f"pexels_{video['id']}.mp4"
        return Media(_download(best["link"], dest), f"pexels:{video['id']}")
    return None


def _pixabay(query: str, used: set[str]) -> Media | None:
    key = env("PIXABAY_API_KEY")
    if not key:
        return None
    resp = requests.get(PIXABAY_URL, params={"key": key, "q": query, "per_page": 20}, timeout=30)
    if resp.status_code != 200:
        return None
    hits = [h for h in resp.json().get("hits", []) if f"pixabay:{h['id']}" not in used and h["duration"] >= 4]
    random.shuffle(hits)
    for hit in hits:
        for size in ("large", "medium"):
            info = hit["videos"].get(size)
            if info and info.get("url"):
                dest = cache_dir() / f"pixabay_{hit['id']}.mp4"
                return Media(_download(info["url"], dest), f"pixabay:{hit['id']}")
    return None


def find_media(query: str, animal: str, used: set[str]) -> Media | None:
    for search in (_pexels, _pixabay):
        for q in (query, animal):
            media = search(q, used)
            if media:
                used.add(media.source_id)
                return media
    return None

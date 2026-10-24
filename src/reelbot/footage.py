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


PEOPLE_TAGS = {
    "man", "men", "woman", "women", "people", "person", "girl", "boy", "child", "children", "family", "crowd",
    "face", "kid", "kids", "couple", "tourist", "tourists", "diver", "swimmer",
    "cartoon", "3d", "2d", "animated", "animation", "ai generated", "ai", "green screen", "illustration",
    "character", "christmas", "santa", "toy", "render", "carousel", "fair", "fairground", "ride", "festival",
    "aerial", "drone", "top view", "bird's eye", "birds eye", "satellite", "silhouette", "map", "sunset", "sunrise",
    "orca", "killer whale", "wallpaper", "fantasy", "screensaver", "porthole", "loop", "background", "abstract",
    "digital", "cgi", "vfx", "effect", "effects", "seamless", "live wallpaper", "cinemagraph", "view from above",
}


def _matches_animal(tags: str, animal: str) -> bool:
    words = [w.lower() for w in animal.replace("-", " ").split()]
    tag_set = {t.strip().lower() for t in tags.split(",") if t.strip()}
    tag_words = {w for t in tag_set for w in t.split()}
    stems = {w[:-1] if w.endswith("s") else w for w in words}
    has_animal = any(t.rstrip("s") in stems or t in words for t in tag_words)
    banned = PEOPLE_TAGS - set(words) - {animal.lower()}
    return has_animal and not ((tag_set | tag_words) & banned)


def _pixabay(query: str, used: set[str], animal: str | None = None) -> Media | None:
    key = env("PIXABAY_API_KEY")
    if not key:
        return None
    resp = requests.get(PIXABAY_URL, params={"key": key, "q": query, "per_page": 50}, timeout=30)
    if resp.status_code != 200:
        return None
    hits = [h for h in resp.json().get("hits", []) if f"pixabay:{h['id']}" not in used and h["duration"] >= 4]
    if animal:
        hits = [h for h in hits if _matches_animal(h.get("tags", ""), animal)]
    random.shuffle(hits)
    for hit in hits:
        for size in ("large", "medium"):
            info = hit["videos"].get(size)
            if info and info.get("url"):
                dest = cache_dir() / f"pixabay_{hit['id']}.mp4"
                return Media(_download(info["url"], dest), f"pixabay:{hit['id']}")
    return None


GENERIC_TERMS = ["", "nature", "wildlife", "closeup", "walking", "eating", "swimming", "baby", "zoo", "slow motion", "habitat"]


@dataclass
class Candidate:
    source_id: str
    url: str
    dest: Path

    def fetch(self) -> Media:
        return Media(_download(self.url, self.dest), self.source_id)


def _pixabay_candidates(query: str, animal: str) -> list[Candidate]:
    key = env("PIXABAY_API_KEY")
    if not key:
        return []
    try:
        resp = requests.get(PIXABAY_URL, params={"key": key, "q": query, "per_page": 50}, timeout=30)
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    found = []
    for hit in resp.json().get("hits", []):
        if hit["duration"] < 4 or not _matches_animal(hit.get("tags", ""), animal):
            continue
        for size in ("large", "medium"):
            info = hit["videos"].get(size)
            if info and info.get("url"):
                found.append(Candidate(f"pixabay:{hit['id']}", info["url"], cache_dir() / f"pixabay_{hit['id']}.mp4"))
                break
    return found


def clip_pool(animal: str, scene_queries: list[str], limit: int = 40, generic: bool = True) -> list[Candidate]:
    """Distinct clips tagged with the animal, scene-specific searches first."""
    seen: set[str] = set()
    pool: list[Candidate] = []
    queries = [q if animal.lower() in q.lower() else f"{animal} {q}" for q in scene_queries]
    if generic:
        queries += [f"{animal} {t}".strip() for t in GENERIC_TERMS]
    for q in queries:
        batch = [c for c in _pixabay_candidates(q, animal) if c.source_id not in seen]
        random.shuffle(batch)
        for c in batch:
            seen.add(c.source_id)
            pool.append(c)
        if len(pool) >= limit:
            break
    return pool


def find_media(query: str, animal: str, used: set[str]) -> Media | None:
    # Every query must contain the animal's name, and Pixabay results must be tagged with it.
    scene_q = query if animal.lower() in query.lower() else f"{animal} {query}"
    for q in (scene_q, animal):
        media = _pixabay(q, used, animal)
        if media:
            used.add(media.source_id)
            return media
    # Reuse clips of the right animal rather than showing something unrelated.
    media = _pixabay(animal, set(), animal)
    if media:
        used.add(media.source_id)
        return media
    for q in (scene_q, animal):
        media = _pexels(q, used)
        if media:
            used.add(media.source_id)
            return media
    return None

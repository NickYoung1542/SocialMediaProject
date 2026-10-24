from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass
class Account:
    name: str
    niche: str
    style: str
    voice: str
    rate: str
    pitch: str
    min_seconds: int
    max_seconds: int
    tiktok_mode: str = "draft"  # "draft" (inbox upload) or "direct" (Direct Post)
    tiktok_privacy: str = "SELF_ONLY"


def load_account(name: str) -> Account:
    path = ROOT / "config" / f"{name}.toml"
    if not path.exists():
        raise SystemExit(f"No account config at {path}")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    voice = raw.get("voice", {})
    video = raw.get("video", {})
    tiktok = raw.get("tiktok", {})
    return Account(
        name=raw["name"],
        niche=raw["niche"],
        style=raw["style"],
        voice=voice.get("name", "en-GB-RyanNeural"),
        rate=voice.get("rate", "+0%"),
        pitch=voice.get("pitch", "+0Hz"),
        min_seconds=video.get("min_seconds", 61),
        max_seconds=video.get("max_seconds", 95),
        tiktok_mode=tiktok.get("mode", "draft"),
        tiktok_privacy=tiktok.get("privacy", "SELF_ONLY"),
    )


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def out_dir() -> Path:
    return ROOT / "out"


def cache_dir() -> Path:
    path = ROOT / "cache"
    path.mkdir(exist_ok=True)
    return path

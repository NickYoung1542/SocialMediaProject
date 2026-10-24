from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from .config import ROOT

DB_PATH = ROOT / "data" / "reelbot.db"
ANIMALS_FILE = ROOT / "data" / "animals.txt"

ANGLES = [
    "how it hunts or finds food",
    "bizarre adaptations and body features",
    "daily life, habitat and social behavior",
    "myths versus facts",
    "record-breaking abilities",
    "life cycle, babies and survival",
    "how it compares to similar animals",
]


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT NOT NULL,
            animal TEXT NOT NULL,
            angle TEXT NOT NULL,
            status TEXT NOT NULL,
            path TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    return conn


def load_animals() -> list[tuple[str, str]]:
    rows = []
    for line in ANIMALS_FILE.read_text(encoding="utf-8").splitlines():
        if "|" in line:
            name, category = line.split("|", 1)
            rows.append((name.strip(), category.strip()))
    return rows


def pick_topic(conn: sqlite3.Connection, account: str, animal: str | None = None) -> tuple[str, str]:
    """Pick the least-used animal and an angle not yet used for it."""
    counts = dict(
        conn.execute(
            "SELECT animal, COUNT(*) FROM videos WHERE account = ? GROUP BY animal", (account,)
        ).fetchall()
    )
    if animal is None:
        names = [name for name, _ in load_animals()]
        fewest = min(counts.get(n, 0) for n in names)
        animal = random.choice([n for n in names if counts.get(n, 0) == fewest])
    used = {
        row[0]
        for row in conn.execute(
            "SELECT angle FROM videos WHERE account = ? AND animal = ?", (account, animal)
        )
    }
    unused = [a for a in ANGLES if a not in used] or ANGLES
    return animal, random.choice(unused)


def next_ready(conn: sqlite3.Connection, account: str) -> tuple[int, str] | None:
    row = conn.execute(
        "SELECT id, path FROM videos WHERE account = ? AND status = 'ready' ORDER BY id LIMIT 1",
        (account,),
    ).fetchone()
    return (row[0], row[1]) if row else None


def set_status(conn: sqlite3.Connection, video_id: int, status: str) -> None:
    conn.execute("UPDATE videos SET status = ? WHERE id = ?", (status, video_id))
    conn.commit()


def record(conn: sqlite3.Connection, account: str, animal: str, angle: str, status: str, path: str) -> None:
    conn.execute(
        "INSERT INTO videos (account, animal, angle, status, path) VALUES (?, ?, ?, ?, ?)",
        (account, animal, angle, status, path),
    )
    conn.commit()

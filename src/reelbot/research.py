from __future__ import annotations

import requests

API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "reelbot/0.1 (educational animal facts project)"}
MAX_CHARS = 9000


class ResearchError(RuntimeError):
    pass


def fetch_source(animal: str) -> tuple[str, str]:
    """Return (page title, plain-text article) from Wikipedia."""
    resp = requests.get(
        API,
        headers=HEADERS,
        params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "redirects": 1,
            "titles": animal,
            "format": "json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    pages = resp.json()["query"]["pages"]
    page = next(iter(pages.values()))
    text = page.get("extract", "")
    if "missing" in page or len(text) < 500:
        raise ResearchError(f"No usable Wikipedia article for {animal!r}")
    return page["title"], text[:MAX_CHARS]

from __future__ import annotations

import argparse
import shutil
import sys

from .config import env, load_account


def doctor() -> int:
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        print(f"[{'ok' if found else 'MISSING'}] {tool}")
        ok &= bool(found)
    provider = env("LLM_PROVIDER", "gemini")
    if provider == "gemini":
        has_key = bool(env("GEMINI_API_KEY"))
        print(f"[{'ok' if has_key else 'MISSING'}] GEMINI_API_KEY (free: https://aistudio.google.com/apikey)")
        ok &= has_key
    else:
        print(f"[ok] LLM provider: {provider}")
    has_footage = bool(env("PEXELS_API_KEY") or env("PIXABAY_API_KEY"))
    print(f"[{'ok' if has_footage else 'MISSING'}] PEXELS_API_KEY or PIXABAY_API_KEY (both free)")
    ok &= has_footage
    has_tiktok = bool(env("TIKTOK_CLIENT_KEY") and env("TIKTOK_CLIENT_SECRET"))
    print(f"[{'ok' if has_tiktok else 'warn'}] TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET (needed for posting)")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="reelbot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, text in (
        ("generate", "Generate one video"),
        ("post", "Post the oldest ready video to TikTok"),
        ("daily", "Generate (if nothing is queued) and post"),
        ("tiktok-auth", "Authorize an account with TikTok (one time)"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("--account", default="animals")
        if name == "generate":
            p.add_argument("--animal", help="Force a specific animal")
    sub.add_parser("doctor", help="Check prerequisites")
    args = parser.parse_args()

    if args.cmd == "doctor":
        return doctor()

    account = load_account(args.account)

    if args.cmd == "generate":
        from .pipeline import generate

        result = generate(account, args.animal)
        print(f"\n{result.status.upper()}: {result.folder}" + (f" ({result.reason})" if result.reason else ""))
        return 0 if result.status == "ready" else 2

    from . import publish, tiktok

    try:
        if args.cmd == "tiktok-auth":
            tiktok.authorize(account)
            return 0
        if args.cmd == "post":
            return 0 if publish.post_next(account) else 2
        return publish.daily(account)
    except tiktok.TikTokError as exc:
        print(f"TikTok error: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())

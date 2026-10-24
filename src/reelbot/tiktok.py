from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .config import ROOT, Account, env

API = "https://open.tiktokapis.com"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
REDIRECT_PORT = 3455
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback/"
SCOPES = {"draft": "video.upload", "direct": "video.publish"}

SINGLE_CHUNK_MAX = 64 * 1024 * 1024
CHUNK_SIZE = 32 * 1024 * 1024
MAX_CAPTION = 2200


class TikTokError(RuntimeError):
    pass


def token_path(account: str) -> Path:
    return ROOT / "data" / f"tiktok_{account}.json"


def make_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    # TikTok wants the hex digest of SHA256, not the base64url form from RFC 7636.
    return verifier, hashlib.sha256(verifier.encode()).hexdigest()


def plan_chunks(size: int) -> list[tuple[int, int]]:
    """Return inclusive (first_byte, last_byte) ranges following TikTok's chunk rules."""
    if size <= SINGLE_CHUNK_MAX:
        return [(0, size - 1)]
    count = size // CHUNK_SIZE
    ranges = [(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE - 1) for i in range(count - 1)]
    ranges.append(((count - 1) * CHUNK_SIZE, size - 1))
    return ranges


def choose_privacy(wanted: str, options: list[str]) -> str:
    if wanted in options:
        return wanted
    return "SELF_ONLY" if "SELF_ONLY" in options else options[0]


def _credentials() -> tuple[str, str]:
    key, secret = env("TIKTOK_CLIENT_KEY"), env("TIKTOK_CLIENT_SECRET")
    if not key or not secret:
        raise TikTokError("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env")
    return key, secret


def _save_tokens(account: str, data: dict) -> dict:
    now = time.time()
    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "open_id": data.get("open_id", ""),
        "scope": data.get("scope", ""),
        "expires_at": now + int(data.get("expires_in", 0)),
        "refresh_expires_at": now + int(data.get("refresh_expires_in", 0)),
    }
    token_path(account).write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    return tokens


def _token_request(payload: dict) -> dict:
    resp = requests.post(
        f"{API}/v2/oauth/token/",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise TikTokError(f"Token request failed: {data.get('error_description') or data}")
    return data


def authorize(account: Account) -> None:
    key, secret = _credentials()
    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(24)
    url = AUTH_URL + "?" + urlencode({
        "client_key": key,
        "scope": SCOPES[account.tiktok_mode],
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    received: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            received.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"reelbot: authorization received. You can close this tab.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("localhost", REDIRECT_PORT), Handler)
    print(f"Opening browser. If it does not open, visit:\n{url}\n")
    webbrowser.open(url)
    server.timeout = 5
    deadline = time.time() + 300
    while not (received.get("code") or received.get("error")) and time.time() < deadline:
        server.handle_request()
    server.server_close()
    if not (received.get("code") or received.get("error")):
        raise TikTokError("Timed out waiting for TikTok authorization")

    if received.get("state") != state:
        raise TikTokError("State mismatch; aborting")
    if "code" not in received:
        raise TikTokError(f"Authorization denied: {received}")
    data = _token_request({
        "client_key": key,
        "client_secret": secret,
        "code": received["code"],
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    })
    _save_tokens(account.name, data)
    print(f"Authorized. Granted scopes: {data.get('scope')}")


def access_token(account: Account) -> str:
    path = token_path(account.name)
    if not path.exists():
        raise TikTokError(f"Not authorized. Run: python -m reelbot tiktok-auth --account {account.name}")
    tokens = json.loads(path.read_text(encoding="utf-8"))
    if tokens["expires_at"] - time.time() > 300:
        return tokens["access_token"]
    if tokens["refresh_expires_at"] <= time.time():
        raise TikTokError("Refresh token expired. Re-run tiktok-auth.")
    key, secret = _credentials()
    data = _token_request({
        "client_key": key,
        "client_secret": secret,
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    })
    return _save_tokens(account.name, data)["access_token"]


def _call(token: str, path: str, body: dict | None = None) -> dict:
    resp = requests.post(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json=body or {},
        timeout=60,
    )
    try:
        data = resp.json()
    except ValueError:
        raise TikTokError(f"{path}: HTTP {resp.status_code} {resp.text[:200]}")
    error = data.get("error", {})
    if error.get("code", "ok") != "ok":
        raise TikTokError(f"{path}: {error.get('code')}: {error.get('message')}")
    return data.get("data", {})


def _upload(upload_url: str, video: Path) -> None:
    size = video.stat().st_size
    with open(video, "rb") as fh:
        for first, last in plan_chunks(size):
            fh.seek(first)
            chunk = fh.read(last - first + 1)
            for attempt in range(3):
                resp = requests.put(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {first}-{last}/{size}",
                    },
                    timeout=300,
                )
                if resp.status_code in (200, 201, 206):
                    break
                if resp.status_code < 500 or attempt == 2:
                    raise TikTokError(f"Upload failed: HTTP {resp.status_code} {resp.text[:200]}")
                time.sleep(3)


def _source_info(video: Path) -> dict:
    size = video.stat().st_size
    chunks = plan_chunks(size)
    return {
        "source": "FILE_UPLOAD",
        "video_size": size,
        "chunk_size": chunks[0][1] - chunks[0][0] + 1 if len(chunks) > 1 else size,
        "total_chunk_count": len(chunks),
    }


def wait_for_status(token: str, publish_id: str, timeout: int = 600) -> str:
    deadline = time.time() + timeout
    status = "UNKNOWN"
    while time.time() < deadline:
        data = _call(token, "/v2/post/publish/status/fetch/", {"publish_id": publish_id})
        status = data.get("status", "UNKNOWN")
        if status == "FAILED":
            raise TikTokError(f"TikTok rejected the post: {data.get('fail_reason')}")
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            return status
        time.sleep(10)
    raise TikTokError(f"Timed out waiting for TikTok (last status {status})")


def publish(account: Account, video: Path, caption: str, log=print) -> str:
    """Upload a video; returns the final TikTok status."""
    token = access_token(account)
    if account.tiktok_mode == "direct":
        info = _call(token, "/v2/post/publish/creator_info/query/")
        privacy = choose_privacy(account.tiktok_privacy, info.get("privacy_level_options", []))
        if privacy != account.tiktok_privacy:
            log(f"Privacy {account.tiktok_privacy} unavailable; using {privacy}")
        max_sec = info.get("max_video_post_duration_sec")
        init = _call(token, "/v2/post/publish/video/init/", {
            "post_info": {
                "title": caption[:MAX_CAPTION],
                "privacy_level": privacy,
                "is_aigc": True,
                "disable_comment": bool(info.get("comment_disabled")),
            },
            "source_info": _source_info(video),
        })
        log(f"Direct post to {info.get('creator_username')} as {privacy} (max {max_sec}s)")
    else:
        init = _call(token, "/v2/post/publish/inbox/video/init/", {"source_info": _source_info(video)})
    _upload(init["upload_url"], video)
    status = wait_for_status(token, init["publish_id"])
    log(f"TikTok status: {status}")
    return status

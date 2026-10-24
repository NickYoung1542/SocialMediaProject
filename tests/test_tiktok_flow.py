import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reelbot import publish, tiktok, topics  # noqa: E402
from reelbot.config import Account  # noqa: E402


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data, self.text = status, data or {}, ""

    def json(self):
        return self._data


def make_account(mode):
    return Account("t", "n", "s", "v", "+0%", "+0Hz", 61, 95, tiktok_mode=mode, tiktok_privacy="PUBLIC_TO_EVERYONE")


def run_flow(monkeypatch, tmp_path, mode):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 1000)
    monkeypatch.setattr(tiktok, "token_path", lambda a: tmp_path / "tok.json")
    (tmp_path / "tok.json").write_text(json.dumps({
        "access_token": "tok", "refresh_token": "r", "expires_at": time.time() + 9999,
        "refresh_expires_at": time.time() + 9999}))
    calls = []

    def fake_post(url, **kw):
        calls.append((url.replace(tiktok.API, ""), kw.get("json")))
        path = calls[-1][0]
        if path.endswith("creator_info/query/"):
            return FakeResp(data={"data": {"privacy_level_options": ["SELF_ONLY"], "creator_username": "me"}, "error": {"code": "ok"}})
        if path.endswith("status/fetch/"):
            status = "PUBLISH_COMPLETE" if mode == "direct" else "SEND_TO_USER_INBOX"
            return FakeResp(data={"data": {"status": status}, "error": {"code": "ok"}})
        return FakeResp(data={"data": {"publish_id": "p1", "upload_url": "https://up/x"}, "error": {"code": "ok"}})

    puts = []
    monkeypatch.setattr(tiktok.requests, "post", fake_post)
    monkeypatch.setattr(tiktok.requests, "put", lambda url, **kw: puts.append(kw["headers"]) or FakeResp(201))
    status = tiktok.publish(make_account(mode), video, "caption #tag", log=lambda *_: None)
    return status, calls, puts


def test_direct_post_forces_private_and_flags_ai(monkeypatch, tmp_path):
    status, calls, puts = run_flow(monkeypatch, tmp_path, "direct")
    init = next(body for path, body in calls if path.endswith("video/init/"))
    assert init["post_info"]["privacy_level"] == "SELF_ONLY"
    assert init["post_info"]["is_aigc"] is True
    assert init["source_info"] == {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1}
    assert puts[0]["Content-Range"] == "bytes 0-999/1000"
    assert status == "PUBLISH_COMPLETE"


def test_draft_mode_uses_inbox_endpoint(monkeypatch, tmp_path):
    status, calls, _ = run_flow(monkeypatch, tmp_path, "draft")
    assert any(path.endswith("inbox/video/init/") for path, _ in calls)
    assert not any(path.endswith("creator_info/query/") for path, _ in calls)
    assert status == "SEND_TO_USER_INBOX"


def test_post_next_marks_video_posted(monkeypatch, tmp_path):
    folder = tmp_path / "vid"
    folder.mkdir()
    (folder / "video.mp4").write_bytes(b"x")
    (folder / "meta.json").write_text(json.dumps({"animal": "Lion", "angle": "a", "caption": "c", "status": "ready"}))
    real_connect = topics.connect
    conn = real_connect(tmp_path / "t.db")
    topics.record(conn, "t", "Lion", "a", "ready", str(folder))
    monkeypatch.setattr(publish.topics, "connect", lambda: real_connect(tmp_path / "t.db"))
    monkeypatch.setattr(publish.tiktok, "publish", lambda *a, **k: "SEND_TO_USER_INBOX")
    assert publish.post_next(make_account("draft"), log=lambda *_: None) is True
    assert json.loads((folder / "meta.json").read_text())["status"] == "posted"
    assert topics.next_ready(real_connect(tmp_path / "t.db"), "t") is None
    assert publish.post_next(make_account("draft"), log=lambda *_: None) is False

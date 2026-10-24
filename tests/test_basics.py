import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reelbot import topics  # noqa: E402
from reelbot.captions import _ts, build_ass  # noqa: E402
from reelbot.llm import _parse_json  # noqa: E402
from reelbot.script import ScriptRejected, _parse  # noqa: E402
from reelbot.tiktok import CHUNK_SIZE, choose_privacy, make_pkce, plan_chunks  # noqa: E402
from reelbot.voice import Word  # noqa: E402


def test_plan_chunks_small_file_is_single_chunk():
    assert plan_chunks(20_000_000) == [(0, 19_999_999)]


def test_plan_chunks_large_file_merges_trailing_bytes():
    size = 3 * CHUNK_SIZE + 123
    ranges = plan_chunks(size)
    assert ranges[0] == (0, CHUNK_SIZE - 1)
    assert ranges[-1][1] == size - 1
    assert all(b == ranges[i + 1][0] - 1 for i, (_, b) in enumerate(ranges[:-1]))
    assert len(ranges) == size // CHUNK_SIZE


def test_pkce_challenge_is_hex_sha256():
    verifier, challenge = make_pkce()
    assert 43 <= len(verifier) <= 128
    assert len(challenge) == 64 and int(challenge, 16) >= 0


def test_choose_privacy_falls_back_to_private():
    assert choose_privacy("PUBLIC_TO_EVERYONE", ["SELF_ONLY"]) == "SELF_ONLY"
    assert choose_privacy("PUBLIC_TO_EVERYONE", ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]) == "PUBLIC_TO_EVERYONE"


def test_next_ready_and_set_status(tmp_path):
    conn = topics.connect(tmp_path / "t.db")
    topics.record(conn, "a", "Lion", topics.ANGLES[0], "held", "x")
    topics.record(conn, "a", "Tiger", topics.ANGLES[0], "ready", "y")
    video_id, path = topics.next_ready(conn, "a")
    assert path == "y"
    topics.set_status(conn, video_id, "posted")
    assert topics.next_ready(conn, "a") is None


def test_parse_json_strips_fences():
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_timestamp_format():
    assert _ts(3661.5) == "1:01:01.50"


def test_build_ass_groups_words(tmp_path):
    words = [Word(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(7)]
    out = tmp_path / "c.ass"
    build_ass(words, out)
    assert out.read_text().count("Dialogue:") == 3


def test_parse_rejects_short_script():
    try:
        _parse({"scenes": [{"text": "one"}]}, "Lion")
    except ScriptRejected:
        return
    raise AssertionError("expected ScriptRejected")


def test_topic_rotation_avoids_repeat_angle(tmp_path):
    conn = topics.connect(tmp_path / "t.db")
    first = topics.pick_topic(conn, "a", "Lion")
    topics.record(conn, "a", *first, "ready", "x")
    second = topics.pick_topic(conn, "a", "Lion")
    assert second[1] != first[1]


def test_unforced_pick_prefers_unused_animal(tmp_path):
    conn = topics.connect(tmp_path / "t.db")
    names = [n for n, _ in topics.load_animals()]
    for name in names[:-1]:
        topics.record(conn, "a", name, topics.ANGLES[0], "ready", "x")
    assert topics.pick_topic(conn, "a")[0] == names[-1]

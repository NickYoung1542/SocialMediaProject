from __future__ import annotations

from pathlib import Path

from .voice import Word

WORDS_PER_CAPTION = 3

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,96,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,2,60,60,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    cs = round(seconds * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(words: list[Word], path: Path) -> None:
    lines = [HEADER]
    for i in range(0, len(words), WORDS_PER_CAPTION):
        chunk = words[i : i + WORDS_PER_CAPTION]
        end = chunk[-1].end
        if i + WORDS_PER_CAPTION < len(words):
            end = max(end, words[i + WORDS_PER_CAPTION].start)
        text = " ".join(w.text for w in chunk).upper().replace("{", "").replace("}", "")
        lines.append(f"Dialogue: 0,{_ts(chunk[0].start)},{_ts(end)},Default,,0,0,0,,{text}\n")
    path.write_text("".join(lines), encoding="utf-8")

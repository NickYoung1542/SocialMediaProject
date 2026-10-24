from __future__ import annotations

from dataclasses import dataclass

from .config import Account
from .llm import generate_json

MIN_WORDS = 170
MAX_WORDS = 230

SCRIPT_PROMPT = """You write narration for a TikTok animal-facts video in the style of a {style}.
Animal: {animal}
Angle: {angle}

Use ONLY facts that appear in the SOURCE TEXT below. Do not invent numbers or claims.
Avoid sweeping absolutes ("every", "all", "always", "never", "only", "the best") and avoid
claims about geographic range unless the source states them exactly. Prefer specific,
concrete facts (numbers, behaviors, body features) copied closely from the source.
Write {min_words}-{max_words} words of narration split into 10-14 scenes.
Rules:
- Scene 1 is a punchy hook (a surprising fact or question) that makes people keep watching.
- The final scene ends with a line that loops back to the hook so viewers rewatch.
- Short, vivid sentences. No emojis, no hashtags, no stage directions, no "in this video".
- Each scene has a "query": 2-4 words to search stock footage for what is being described
  (always include the animal name, e.g. "{animal} hunting").

Return JSON only:
{{"title": "...", "scenes": [{{"text": "...", "query": "..."}}],
 "caption": "one or two sentences for the TikTok caption", "hashtags": ["#animalfacts", "..."]}}

SOURCE TEXT:
{source}
"""

CHECK_PROMPT = """You are a fact-checker. Compare the NARRATION to the SOURCE TEXT.
Flag a claim only if the source text contradicts it, or it states a specific fact
(number, behavior, ability, absolute) that the source does not support.
Do NOT flag simplifications, rephrasing, rhetorical hooks, or things merely left out.

Return JSON only: {{"ok": true or false, "issues": ["unsupported claim", ...]}}
Set "ok" to true only if every factual claim is supported.

NARRATION:
{narration}

SOURCE TEXT:
{source}
"""

RETRY_NOTE = "\nA previous draft had these unsupported claims; do not repeat them: {issues}\n"


@dataclass
class Scene:
    text: str
    query: str


@dataclass
class Script:
    title: str
    scenes: list[Scene]
    caption: str
    hashtags: list[str]

    @property
    def narration(self) -> str:
        return " ".join(s.text for s in self.scenes)

    @property
    def word_count(self) -> int:
        return len(self.narration.split())


class ScriptRejected(RuntimeError):
    pass


def _parse(data: dict, animal: str) -> Script:
    scenes = [
        Scene(
            text=str(s["text"]).strip(),
            query=str(s.get("query") or animal).strip(),
        )
        for s in data["scenes"]
        if str(s.get("text", "")).strip()
    ]
    if len(scenes) < 6:
        raise ScriptRejected("Script has too few scenes")
    tags = [t if t.startswith("#") else f"#{t}" for t in data.get("hashtags", [])]
    return Script(data.get("title", animal), scenes, data.get("caption", ""), tags)


def write_script(account: Account, animal: str, angle: str, source: str, attempts: int = 3) -> Script:
    note = ""
    last_issues: list[str] = []
    for _ in range(attempts):
        prompt = SCRIPT_PROMPT.format(
            style=account.style,
            animal=animal,
            angle=angle,
            min_words=MIN_WORDS,
            max_words=MAX_WORDS,
            source=source,
        ) + note
        try:
            script = _parse(generate_json(prompt), animal)
        except (KeyError, TypeError, ScriptRejected) as exc:
            last_issues = [f"malformed script: {exc}"]
            continue
        if not MIN_WORDS - 20 <= script.word_count <= MAX_WORDS + 30:
            last_issues = [f"script was {script.word_count} words, need {MIN_WORDS}-{MAX_WORDS}"]
            note = RETRY_NOTE.format(issues=last_issues)
            continue
        verdict = generate_json(CHECK_PROMPT.format(narration=script.narration, source=source))
        if verdict.get("ok") is True:
            return script
        last_issues = [str(i) for i in verdict.get("issues", ["fact check failed"])]
        note = RETRY_NOTE.format(issues=last_issues)
    raise ScriptRejected("; ".join(last_issues))

from __future__ import annotations

import json
import re
import time
import requests

from .config import env


class LLMError(RuntimeError):
    pass


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise LLMError(f"LLM did not return JSON: {text[:200]}")
        return json.loads(match.group(0))


def generate_json(prompt: str) -> dict:
    provider = env("LLM_PROVIDER", "gemini").lower()
    if provider == "gemini":
        return _gemini(prompt)
    if provider == "ollama":
        return _ollama(prompt)
    raise LLMError(f"Unknown LLM_PROVIDER: {provider}")


GEMINI_FALLBACKS = ["gemini-3.5-flash", "gemini-3.1-flash-lite"]
RETRYABLE = {429, 500, 502, 503, 504}


def _gemini(prompt: str) -> dict:
    key = env("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY is not set (free key: https://aistudio.google.com/apikey)")
    primary = env("GEMINI_MODEL", "gemini-3.8-flash")
    models = [primary] + [m for m in GEMINI_FALLBACKS if m != primary]
    last = ""
    for model in models:
        for attempt in range(2):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                resp = requests.post(
                    url,
                    headers={"x-goog-api-key": key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7},
                    },
                    timeout=60,
                )
            except requests.RequestException as exc:
                last = f"{model}: {type(exc).__name__}"
                time.sleep(3)
                continue
            if resp.status_code == 200:
                try:
                    return _parse_json(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
                except (KeyError, IndexError, LLMError, json.JSONDecodeError) as exc:
                    last = f"{model}: bad response ({exc})"
                    break
            last = f"{model}: HTTP {resp.status_code} {resp.text[:150]}"
            if resp.status_code not in RETRYABLE:
                break
            time.sleep(4 * (attempt + 1))
    raise LLMError(f"All Gemini models failed. Last error: {last}")


def _ollama(prompt: str) -> dict:
    model = env("OLLAMA_MODEL", "llama3.1:8b")
    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "format": "json",
                "stream": False,
            },
            timeout=600,
        )
    except requests.ConnectionError as exc:
        raise LLMError("Ollama is not running (install from https://ollama.com)") from exc
    if resp.status_code != 200:
        raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
    return _parse_json(resp.json()["message"]["content"])

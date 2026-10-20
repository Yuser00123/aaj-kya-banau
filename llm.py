"""
llm.py — one tiny wrapper, three ways to run Gemma (same engine as our earlier Pakshi Padosi).

    LLM_PROVIDER=openai  (default)  any OpenAI-compatible endpoint:
                                     Google AI Studio (Gemma 4), Ollama (offline!),
                                     Groq, OpenRouter, DigitalOcean Gradient...
    LLM_PROVIDER=google             native google-genai SDK (Gemini API)
    LLM_PROVIDER=mock               deterministic replies, zero network

Because Gemma's weights are open, the SAME model can be served by Google for free, by Ollama on
the café's own PC with no internet, or by any other provider — swapping is two environment
variables. That is the whole point of this file.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List

Message = Dict[str, str]

PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
MODEL = os.getenv("LLM_MODEL", "gemma-4-31b-it").strip()
BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/").strip()
API_KEY = (
    os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    or "not-needed"  # Ollama ignores the key but the SDK wants a non-empty string
).strip()
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4000"))  # Gemma 4 thinks before it answers; thinking eats tokens
FOLD_SYSTEM = os.getenv("FOLD_SYSTEM", "0") == "1"


class LLMError(RuntimeError):
    """Raised with a short, friendly Hindi message that the UI can show directly."""


# ------------------------------------------------------------------ thinking filter
# Gemma 4 may emit its chain of thought inline as <thought>…</thought> before the answer.
# The applicant's letter must never show it.
_OPEN_TAGS = ("<thought>", "<think>")
_CLOSE_TAGS = ("</thought>", "</think>")
_MAX_TAG = max(len(t) for t in _CLOSE_TAGS)


def _find_first(text: str, tags) -> tuple[int, str]:
    best, best_tag = -1, ""
    for tag in tags:
        i = text.find(tag)
        if i != -1 and (best == -1 or i < best):
            best, best_tag = i, tag
    return best, best_tag


class ThoughtFilter:
    def __init__(self) -> None:
        self.in_thought = False
        self.buf = ""

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        out = ""
        while True:
            if self.in_thought:
                i, tag = _find_first(self.buf, _CLOSE_TAGS)
                if i == -1:
                    self.buf = self.buf[-(_MAX_TAG - 1):]
                    return out
                self.buf = self.buf[i + len(tag):].lstrip("\n")
                self.in_thought = False
            else:
                i, tag = _find_first(self.buf, _OPEN_TAGS)
                if i == -1:
                    keep = 0
                    for tag in _OPEN_TAGS:  # longest suffix that may be a split opening tag
                        for k in range(min(len(tag) - 1, len(self.buf)), 0, -1):
                            if self.buf.endswith(tag[:k]):
                                keep = max(keep, k)
                                break
                    out += self.buf[: len(self.buf) - keep]
                    self.buf = self.buf[len(self.buf) - keep:]
                    return out
                out += self.buf[:i]
                self.buf = self.buf[i + len(tag):]
                self.in_thought = True

    def flush(self) -> str:
        out = "" if self.in_thought else self.buf
        self.buf = ""
        return out


def strip_thoughts(text: str) -> str:
    f = ThoughtFilter()
    out = f.feed(text) + f.flush()
    if not out.strip() and f.in_thought:
        raise LLMError("Gemma sochte-sochte token limit paar kar gaya. Dobara try karo (ya LLM_MAX_TOKENS badhao).")
    return out.lstrip("\n")


def _log(msg: str) -> None:
    if os.getenv("LLM_QUIET", "").lower() not in ("1", "true", "yes"):
        print(f"[llm] {msg}", flush=True)


def _retryable(err: Exception) -> bool:
    low = str(err).lower()
    return any(k in low for k in ("429", "rate", "quota", "500", "502", "503", "504", "internal", "overloaded", "unavailable", "timed out", "timeout"))


def describe() -> str:
    if PROVIDER == "mock":
        return "mock (koi model nahi — LLM_API_KEY set karo)"
    if PROVIDER == "google":
        return f"{MODEL} via Gemini API (google-genai)"
    host = re.sub(r"^https?://", "", BASE_URL).split("/")[0]
    return f"{MODEL} via {host}"


def available() -> bool:
    return PROVIDER != "mock" and API_KEY != "not-needed"


# ------------------------------------------------------------------ helpers
def _fold_system(messages: List[Message]) -> List[Message]:
    if not messages or messages[0]["role"] != "system":
        return messages
    system, rest = messages[0]["content"], list(messages[1:])
    if rest and rest[0]["role"] == "user":
        rest[0] = {"role": "user", "content": f"{system}\n\n---\n\n{rest[0]['content']}"}
    else:
        rest.insert(0, {"role": "user", "content": system})
    return rest


def _looks_like_system_role_error(err: Exception) -> bool:
    text = str(err).lower()
    return "system" in text or "developer instruction" in text


def _friendly(err: Exception) -> LLMError:
    text = str(err)
    low = text.lower()
    if "429" in low or "rate" in low or "quota" in low or "resource_exhausted" in low:
        return LLMError("Gemma abhi vyast hai (rate limit) — 20-30 second ruk ke dobara daba.")
    if "401" in low or "403" in low or "api key" in low or "permission" in low:
        return LLMError("API key galat ya gayab hai (LLM_API_KEY check karo).")
    if "404" in low or "not found" in low:
        return LLMError(f"Model provider par nahi mila (LLM_MODEL check karo).")
    if "connection" in low or "connect" in low or "timed out" in low or "timeout" in low:
        return LLMError("Model server se connect nahi ho paya — internet / Ollama chalu hai?")
    return LLMError(f"मॉडल त्रुटि: {text[:200]}")


def parse_json(text: str) -> dict:
    """Lenient JSON extraction: strips code fences and trims to the outermost {...}."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Model se valid JSON nahi mila — dobara try karo.")
        return json.loads(cleaned[start: end + 1])


# ------------------------------------------------------------------ providers
def _openai_chat(messages: List[Message], json_mode: bool, temperature: float, max_tokens: int):
    from openai import OpenAI  # imported lazily so `mock` mode needs no SDK

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=120, max_retries=0)
    kwargs = dict(model=MODEL, messages=messages, temperature=temperature, max_tokens=max_tokens)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as err:  # noqa: BLE001 — translate and adapt
        low = str(err).lower()
        if json_mode and ("response_format" in low or "json" in low):     # provider can't do json mode
            kwargs.pop("response_format", None)
            return client.chat.completions.create(**kwargs)
        if _looks_like_system_role_error(err) and messages and messages[0]["role"] == "system":
            kwargs["messages"] = _fold_system(messages)                   # fold system into user turn
            return client.chat.completions.create(**kwargs)
        raise


def _google_chat(messages: List[Message], json_mode: bool, temperature: float, max_tokens: int):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=API_KEY)
    system, contents = None, []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
            continue
        contents.append(types.Content(role="model" if m["role"] == "assistant" else "user",
                                      parts=[types.Part(text=m["content"])]))
    config = types.GenerateContentConfig(
        temperature=temperature, max_output_tokens=max_tokens, system_instruction=system,
        response_mime_type="application/json" if json_mode else None)
    return client.models.generate_content(model=MODEL, contents=contents, config=config)


# ------------------------------------------------------------------ mock
MOCK_HANDLER = None  # the app registers a function(messages, json_mode) -> str for offline/demo mode


def _mock_text(messages: List[Message], json_mode: bool) -> str:
    if MOCK_HANDLER is not None:
        return MOCK_HANDLER(messages, json_mode)
    user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if json_mode:
        return json.dumps({"mock": True, "echo": user[:200]}, ensure_ascii=False)
    return f"(मॉक मोड — Gemma जुड़ा नहीं है। .env में LLM_API_KEY डालें।)\n\n{user[:400]}"


# ------------------------------------------------------------------ public API
def chat(messages: List[Message], json_mode: bool = False, temperature: float | None = None,
         max_tokens: int | None = None, budget: float | None = None) -> str:
    """Full assistant reply (thinking removed). Retries rate limits and transient 5xx.

    `budget` (seconds): no new attempt starts once this much time has passed."""
    temperature = TEMPERATURE if temperature is None else temperature
    max_tokens = MAX_TOKENS if max_tokens is None else max_tokens
    if PROVIDER == "mock":
        time.sleep(0.3)
        return _mock_text(messages, json_mode)
    if FOLD_SYSTEM and PROVIDER == "openai":
        messages = _fold_system(messages)

    delays = (0, 3, 6, 6)
    last_err: Exception | None = None
    started = time.time()
    for attempt, delay in enumerate(delays, 1):
        if budget is not None and attempt > 1 and time.time() - started + delay > budget:
            _log(f"chat budget {budget:.0f}s spent after {attempt - 1} attempt(s); giving up")
            break
        if delay:
            time.sleep(delay)
        t0 = time.time()
        try:
            if PROVIDER == "google":
                resp = _google_chat(messages, json_mode, temperature, max_tokens)
                text = resp.text or ""
            else:
                resp = _openai_chat(messages, json_mode, temperature, max_tokens)
                text = resp.choices[0].message.content or ""
            visible = strip_thoughts(text)
            _log(f"chat attempt={attempt} {time.time() - t0:.1f}s raw={len(text)} visible={len(visible.strip())}")
            if visible.strip():
                return visible
            last_err = LLMError("Model se khaali jawab aaya — dobara try karo.")
        except LLMError as err:
            _log(f"chat attempt={attempt} {time.time() - t0:.1f}s empty: {err}")
            last_err = err
        except Exception as err:  # noqa: BLE001
            _log(f"chat attempt={attempt} {time.time() - t0:.1f}s error={str(err)[:160]!r}")
            last_err = err
            if not _retryable(err):
                break
    if isinstance(last_err, LLMError):
        raise last_err
    raise _friendly(last_err or RuntimeError("अनजानी त्रुटि"))

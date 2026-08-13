"""
llm_client.py — 3-Tier Multi-Provider LLM Waterfall Client.

Every LLM call (script, decisions, facts, metadata) goes through:

  Tier 1 → OpenCode Zen (deepseek-v4-flash-free)
  Tier 2 → Groq 10-Key Pool (openai/gpt-oss-120b)  — Keys 1-10
  Tier 3 → Google Gemini AI Studio (gemini-2.5-flash-lite)

Rules:
  - Always starts fresh at Tier 1 for every call.
  - Each candidate gets exactly 1 attempt — no retries, no sleep.
  - If a candidate fails (429, 5xx, timeout, empty), it instantly
    cascades to the next key/provider in under 0.5s.
  - If a JSON call returns text that can't be parsed as JSON,
    the next candidate is tried immediately.
  - JSON is clean regardless of which tier handled the call.
"""

import json
from openai import OpenAI
from . import config


# ── Candidate builder ──────────────────────────────────────────────────────────

def _build_waterfall() -> list[dict]:
    """
    Returns the full ordered list of LLM candidates to try.
    Each entry: {"label": str, "client": OpenAI, "model": str}
    """
    candidates = []

    # ── Tier 1A: OpenCode Zen ─────────────────────────────────────────────────
    if config.LLM_API_KEY and config.LLM_BASE_URL:
        candidates.append({
            "label": f"Tier 1A — OpenCode Zen ({config.LLM_MODEL})",
            "client": OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY),
            "model": config.LLM_MODEL,
        })

    # ── Tier 1B: OpenRouter DeepSeek V4 Flash ────────────────────────────────
    if getattr(config, "OPENROUTER_API_KEY", ""):
        candidates.append({
            "label": f"Tier 1B — OpenRouter ({config.OPENROUTER_MODEL})",
            "client": OpenAI(
                base_url=config.OPENROUTER_BASE_URL,
                api_key=config.OPENROUTER_API_KEY,
                default_headers={
                    "HTTP-Referer": "https://github.com/1919-14/YT-Automation",
                    "X-Title": "Night Loom YouTube Automation",
                }
            ),
            "model": config.OPENROUTER_MODEL,
        })


    # ── Tier 2: Groq 10-Key Pool ──────────────────────────────────────────────
    for idx, key in enumerate(config.GROQ_API_KEYS, start=1):
        candidates.append({
            "label": f"Tier 2 — Groq Key {idx} ({config.GROQ_MODEL})",
            "client": OpenAI(base_url=config.GROQ_BASE_URL, api_key=key),
            "model": config.GROQ_MODEL,
        })

    # ── Tier 3: Google Gemini AI Studio ───────────────────────────────────────
    if config.GEMINI_API_KEY:
        candidates.append({
            "label": f"Tier 3 — Gemini AI Studio ({config.GEMINI_MODEL})",
            "client": OpenAI(base_url=config.GEMINI_BASE_URL, api_key=config.GEMINI_API_KEY),
            "model": config.GEMINI_MODEL,
        })

    return candidates


# ── Core waterfall call ────────────────────────────────────────────────────────

def chat(messages: list[dict], temperature: float = 0.9, **kwargs) -> str:
    """
    Plain-text LLM completion with 3-tier waterfall failover.
    messages = [{"role": "user", "content": "..."}]

    Tries each candidate exactly once. On any failure, instantly
    cascades to the next. Raises only if every candidate fails.
    """
    candidates = _build_waterfall()
    errors = []

    for candidate in candidates:
        label = candidate["label"]
        try:
            resp = candidate["client"].chat.completions.create(
                model=candidate["model"],
                messages=messages,
                temperature=temperature,
                **kwargs,
            )
            content = resp.choices[0].message.content
            if content and content.strip():
                print(f"[llm] OK: {label}")
                return content.strip()
            else:
                raise ValueError("Empty response returned")
        except Exception as e:
            err_short = str(e)[:120]
            try:
                print(f"[llm] FAIL: {label} -> {err_short}")
            except Exception:
                pass
            errors.append(f"{label}: {err_short}")

    raise RuntimeError(
        f"All LLM providers exhausted across {len(candidates)} candidates.\n"
        + "\n".join(errors)
    )


def chat_json(messages: list[dict], temperature: float = 0.7, **kwargs) -> dict:
    """
    JSON-validated LLM completion with 3-tier waterfall failover.

    Tries each candidate exactly once. If a candidate's output cannot
    be parsed as valid JSON, it immediately tries the next candidate.
    Raises only if every candidate fails to return valid JSON.
    """
    candidates = _build_waterfall()
    errors = []

    for candidate in candidates:
        label = candidate["label"]
        raw = None
        try:
            resp = candidate["client"].chat.completions.create(
                model=candidate["model"],
                messages=messages,
                temperature=temperature,
                **kwargs,
            )
            raw = resp.choices[0].message.content
            if not raw or not raw.strip():
                raise ValueError("Empty response returned")

            # Strip markdown code fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                parts = cleaned.split("```")
                cleaned = parts[1] if len(parts) > 1 else cleaned
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            print(f"[llm] OK JSON: {label}")
            return parsed

        except json.JSONDecodeError as e:
            snippet = (raw or "")[:200]
            msg = f"{label}: JSON parse failed - {e} | raw: {snippet}"
            try:
                print(f"[llm] FAIL JSON: {msg}")
            except Exception:
                pass
            errors.append(msg)
        except Exception as e:
            err_short = str(e)[:120]
            try:
                print(f"[llm] FAIL: {label} -> {err_short}")
            except Exception:
                pass
            errors.append(f"{label}: {err_short}")

    raise RuntimeError(
        f"All LLM providers exhausted across {len(candidates)} candidates.\n"
        + "\n".join(errors)
    )


# ── Smoke test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Waterfall Smoke Test ===")
    # Text
    reply = chat([{"role": "user", "content": "Say 'pipeline online' and nothing else."}])
    print("Text reply:", reply)

    # JSON
    data = chat_json([{"role": "user", "content": 'Return valid JSON: {"status": "ok", "pipeline": "online"}'}])
    print("JSON reply:", data)

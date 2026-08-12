"""
llm_client.py — thin wrapper around the OpenAI-compatible chat completions
endpoint (OpenCode Zen / DeepSeek V4 by default, per .env).

Everything that needs an LLM call goes through chat() or chat_json()
here, not through the SDK directly — keeps retry/error handling and
provider swaps in one place.
"""

import json
import time
from openai import OpenAI
from . import config

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    return _client


def chat(messages, temperature=0.9, max_retries=5, **kwargs):
    """Plain text completion. messages = [{"role": "user", "content": "..."}]"""
    client = get_client()
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                temperature=temperature,
                **kwargs,
            )
            return resp.choices[0].message.content
        except Exception as e:
            last_err = e
            err_str = str(e)
            # If 429 rate limit / FreeUsageLimitError, back off longer (5s, 10s, 15s...)
            if "429" in err_str or "Rate limit" in err_str or "FreeUsageLimitError" in err_str:
                wait = (attempt + 1) * 5
                print(f"[llm_client] Rate limit hit (attempt {attempt + 1}/{max_retries}). Backing off for {wait}s...")
            else:
                wait = 2 ** attempt
                print(f"[llm_client] attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_err}")


def chat_json(messages, temperature=0.7, max_retries=5, **kwargs):
    """Completion that must return valid JSON. Strips markdown code fences
    if the model wraps its output in them, and retries on parse failure."""
    last_err = None
    for attempt in range(max_retries):
        try:
            raw = chat(messages, temperature=temperature, max_retries=max_retries, **kwargs)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_err = e
            print(f"[llm_client] JSON parse failed on attempt {attempt + 1}: {e}")
            print(f"[llm_client] raw output was: {raw[:300] if 'raw' in locals() else 'None'}")
            time.sleep(2)
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"chat_json failed after {max_retries} attempts: {last_err}")



if __name__ == "__main__":
    # quick smoke test
    reply = chat([{"role": "user", "content": "Say 'pipeline online' and nothing else."}])
    print("Response:", reply)

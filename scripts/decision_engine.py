"""decision_engine.py — policy for choosing the next Night Loom video."""

import os
import random
from datetime import datetime, timezone

from . import memory as mem
from . import llm_client
from .categories import list_categories, get_category_config
from . import learning_engine

STALE_DAYS_THRESHOLD = 1
NEW_SERIES_PROBABILITY = 0.6


def _days_since(iso_timestamp):
    if not iso_timestamp:
        return None
    dt = datetime.fromisoformat(iso_timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def _pick_category(conn, exclude_last_n=2, format_="short"):
    recent = set(mem.recent_categories(conn, limit=exclude_last_n))
    candidates = [c for c in list_categories() if c not in recent] or list_categories()
    try:
        learned = learning_engine.choose_category(conn, format_)
        if learned in candidates and random.random() < 0.70:
            return learned
    except Exception as exc:
        print(f"[decision_engine] Learning prior unavailable: {exc}")
    return random.choice(candidates)


def _judge_continue_or_conclude(series):
    prompt = f"""You are the showrunner for a story series on a YouTube storytelling channel.

Series: "{series['series_name']}" (category: {series['category']})
Current part: {series['current_part']}
Total parts planned: {series['total_parts_planned'] or 'open-ended'}
Last episode summary: {series['last_episode_summary']}
Unresolved threads: {series['unresolved_threads']}
Days since last episode: {series.get('_days_since')}

Decide whether the NEXT episode should CONTINUE the series (introduce or advance a thread) or CONCLUDE it (resolve remaining threads and end the story satisfyingly).

Respond with ONLY valid JSON, no markdown, no explanation:
{{"action": "continue" or "conclude", "reason": "one sentence why"}}"""
    return llm_client.chat_json([{"role": "user", "content": prompt}], temperature=0.4)


def decide_next_video(conn, is_short: bool | None = None):
    """Choose the next video using mature performance as a soft category prior.

    The scheduler sets NIGHTLOOM_FORMAT before launching a slot so long-form
    and short-form learning remain separate without changing the existing
    orchestrator API.
    """
    if is_short is None:
        is_short = os.getenv("NIGHTLOOM_FORMAT", "short") != "long_continuous"

    active_series = mem.get_active_series(conn)
    for s in active_series:
        s["_days_since"] = _days_since(s.get("last_video_date"))

    stale_candidates = [s for s in active_series if (s["_days_since"] or 0) >= STALE_DAYS_THRESHOLD]
    if stale_candidates:
        target = stale_candidates[0]
        judgment = _judge_continue_or_conclude(target)
        action = "continue_series" if judgment["action"] == "continue" else "conclude_series"
        return {"action": action, "series_id": target["series_id"], "category": target["category"], "reason": judgment["reason"]}

    if active_series and random.random() < 0.4:
        target = active_series[0]
        return {"action": "continue_series", "series_id": target["series_id"], "category": target["category"], "reason": "Active series continuing on normal cadence."}

    format_ = "short" if is_short else "long_continuous"
    category = _pick_category(conn, format_=format_)
    cat_config = get_category_config(category)

    if cat_config["series_friendly"] and random.random() < NEW_SERIES_PROBABILITY:
        return {"action": "new_content", "series_id": None, "category": category, "reason": f"Starting a new series in category '{category}'.", "start_new_series": True}

    return {"action": "new_content", "series_id": None, "category": category, "reason": f"Standalone video in category '{category}'.", "start_new_series": False}


if __name__ == "__main__":
    mem.init_db()
    with mem.get_conn() as conn:
        print("Decision:", decide_next_video(conn))

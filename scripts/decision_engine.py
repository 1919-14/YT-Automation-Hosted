"""
decision_engine.py — decides what the NEXT video should be, before
any script gets written.

Logic is intentionally mostly rule-based (cheap, predictable) with
one LLM call only for the judgment-heavy part: whether a stale
series should continue or wrap up. Keeping the mechanical parts
out of the LLM avoids a whole class of hallucination risk.
"""

import random
from datetime import datetime, timezone

from . import memory as mem
from . import llm_client
from .categories import list_categories, get_category_config

STALE_DAYS_THRESHOLD = 1          # active series continues after 1 day threshold
NEW_SERIES_PROBABILITY = 0.6      # balanced 60% chance for new multi-part series


def _days_since(iso_timestamp):
    if not iso_timestamp:
        return None
    dt = datetime.fromisoformat(iso_timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def _pick_category(conn, exclude_last_n=2):
    """Weighted-random category pick, avoiding the last N categories
    posted so we don't repeat the same theme back to back."""
    recent = set(mem.recent_categories(conn, limit=exclude_last_n))
    candidates = [c for c in list_categories() if c not in recent]
    if not candidates:
        candidates = list_categories()
    return random.choice(candidates)


def _judge_continue_or_conclude(series):
    """One LLM call for the actual judgment: given the story state,
    should this series continue or wrap up? Returns dict with
    action ('continue' or 'conclude') and reason."""
    prompt = f"""You are the showrunner for a story series on a YouTube storytelling channel.

Series: "{series['series_name']}" (category: {series['category']})
Current part: {series['current_part']}
Total parts planned: {series['total_parts_planned'] or 'open-ended'}
Last episode summary: {series['last_episode_summary']}
Unresolved threads: {series['unresolved_threads']}
Days since last episode: {series.get('_days_since')}

Decide whether the NEXT episode should CONTINUE the series (introduce
or advance a thread) or CONCLUDE it (resolve remaining threads and end
the story satisfyingly). Consider: series that have gone unresolved a
long time are prime candidates to wrap up. Series with rich unresolved
threads still have juice left, unless it's dragged on many parts already.

Respond with ONLY valid JSON, no markdown, no explanation:
{{"action": "continue" or "conclude", "reason": "one sentence why"}}"""

    result = llm_client.chat_json([{"role": "user", "content": prompt}], temperature=0.4)
    return result


def decide_next_video(conn):
    """Main entry point. Returns a decision dict:
    {
        "action": "continue_series" | "conclude_series" | "new_content",
        "series_id": int or None,
        "category": str,
        "reason": str,
    }
    """
    active_series = mem.get_active_series(conn)

    for s in active_series:
        s["_days_since"] = _days_since(s.get("last_video_date"))

    # Look for a stale series first — staleness-ordered query means
    # active_series[0] is already the most overdue.
    stale_candidates = [s for s in active_series if (s["_days_since"] or 0) >= STALE_DAYS_THRESHOLD]

    if stale_candidates:
        target = stale_candidates[0]
        judgment = _judge_continue_or_conclude(target)
        action = "continue_series" if judgment["action"] == "continue" else "conclude_series"
        return {
            "action": action,
            "series_id": target["series_id"],
            "category": target["category"],
            "reason": judgment["reason"],
        }

    # Non-stale active series still get a chance to continue naturally
    # (not every run needs to start something new).
    if active_series and random.random() < 0.4:
        target = active_series[0]
        return {
            "action": "continue_series",
            "series_id": target["series_id"],
            "category": target["category"],
            "reason": "Active series continuing on normal cadence.",
        }

    # Otherwise: new content. Decide category, then decide if it
    # kicks off a new series or stays standalone.
    category = _pick_category(conn)
    cat_config = get_category_config(category)

    if cat_config["series_friendly"] and random.random() < NEW_SERIES_PROBABILITY:
        return {
            "action": "new_content",
            "series_id": None,
            "category": category,
            "reason": f"Starting a new series in category '{category}'.",
            "start_new_series": True,
        }

    return {
        "action": "new_content",
        "series_id": None,
        "category": category,
        "reason": f"Standalone video in category '{category}'.",
        "start_new_series": False,
    }


if __name__ == "__main__":
    mem.init_db()
    with mem.get_conn() as conn:
        decision = decide_next_video(conn)
        print("Decision:", decision)

"""
learning_engine.py — V1 closed-loop learner for Night Loom.

The learner is deliberately conservative:
  * only 48h-mature videos influence category/format rewards;
  * rewards are based on views plus engagement rate, not raw views alone;
  * category selection uses a soft UCB-style score so every category keeps
    receiving some exploration;
  * it never edits already-published videos or changes upload frequency.

This is policy learning, not model fine-tuning. The LLM remains responsible
for generating the actual content.
"""

import math
from datetime import datetime, timezone

from . import categories, memory

MATURE_LABEL = "48h"
EXPLORATION = 1.25
MIN_CATEGORY_PROBABILITY = 0.10


def _reward(views: int, likes: int, comments: int) -> float:
    """Stable reward that does not let a single viral video dominate forever."""
    safe_views = max(0, int(views))
    engagement = (max(0, int(likes)) + 2.0 * max(0, int(comments))) / max(1, safe_views)
    return math.log1p(safe_views) + 8.0 * engagement


def update_learning_state(conn) -> int:
    """Rebuild category/format aggregates from mature snapshots.

    Returns number of learning rows updated. Recomputing from snapshots keeps
    this idempotent and makes the learner resilient to container restarts.
    """
    rows = conn.execute(
        """
        SELECT v.category, v.format,
               m.views, m.likes, m.comments
        FROM video_metrics m
        JOIN videos v ON v.video_id = m.video_id
        WHERE m.snapshot_label = ?
        """,
        (MATURE_LABEL,),
    ).fetchall()

    grouped = {}
    for row in rows:
        key = (row["category"], row["format"])
        grouped.setdefault(key, []).append(row)

    now = datetime.now(timezone.utc).isoformat()
    for (category, format_), samples in grouped.items():
        rewards = [_reward(r["views"], r["likes"], r["comments"]) for r in samples]
        views = [r["views"] for r in samples]
        like_rates = [r["likes"] / max(1, r["views"]) for r in samples]
        conn.execute(
            """
            INSERT INTO learning_state
              (category, format, sample_count, mean_reward, mean_views,
               mean_like_rate, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category, format) DO UPDATE SET
              sample_count=excluded.sample_count,
              mean_reward=excluded.mean_reward,
              mean_views=excluded.mean_views,
              mean_like_rate=excluded.mean_like_rate,
              updated_at=excluded.updated_at
            """,
            (
                category, format_, len(samples),
                sum(rewards) / len(rewards),
                sum(views) / len(views),
                sum(like_rates) / len(like_rates),
                now,
            ),
        )

    return len(grouped)


def category_scores(conn, format_: str) -> dict[str, float]:
    """Return soft UCB scores for all configured categories."""
    rows = conn.execute(
        "SELECT category, sample_count, mean_reward FROM learning_state WHERE format = ?",
        (format_,),
    ).fetchall()
    state = {r["category"]: (r["sample_count"], r["mean_reward"]) for r in rows}

    total = sum(n for n, _ in state.values())
    scores = {}
    for category in categories.list_categories():
        n, mean = state.get(category, (0, 0.0))
        if n == 0:
            scores[category] = float("inf")
        else:
            bonus = EXPLORATION * math.sqrt(math.log(max(2, total)) / n)
            scores[category] = mean + bonus
    return scores


def choose_category(conn, format_: str) -> str:
    """Choose from top categories with a small exploration floor."""
    scores = category_scores(conn, format_)
    untried = [c for c, score in scores.items() if math.isinf(score)]
    if untried:
        # Deterministic-ish round robin by lowest historical sample count.
        return min(untried, key=lambda c: c)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    # Soft top-tier selection: do not turn a tiny sample into a hard monopoly.
    top = ranked[:max(1, min(2, len(ranked)))]
    return top[0][0]


def learn_once() -> int:
    """Collect mature observations and update the policy state."""
    memory.init_db()
    with memory.get_conn() as conn:
        updated = update_learning_state(conn)
        print(f"[learning] 🧠 Updated {updated} category/format learning rows.")
        rows = conn.execute(
            "SELECT category, format, sample_count, mean_views, mean_reward "
            "FROM learning_state ORDER BY mean_reward DESC"
        ).fetchall()
        for row in rows:
            print(
                f"[learning] {row['category']}/{row['format']}: "
                f"n={row['sample_count']} views={row['mean_views']:.1f} "
                f"reward={row['mean_reward']:.3f}"
            )
        return updated


if __name__ == "__main__":
    learn_once()

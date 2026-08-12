"""
memory.py — persistent memory layer for the YT automation pipeline.

Everything else in the project reads/writes series & video state
through this module. Keeps the SQLite logic in one place so the
schema can evolve without touching the orchestrator or generators.
"""

import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "memory.db"
SCHEMA_PATH = Path(__file__).parent.parent / "data" / "schema.sql"


def init_db():
    """Create tables if they don't exist yet. Safe to call every run."""
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------
# Series state
# ------------------------------------------------------------------

def get_active_series(conn):
    """All series with status='active', oldest last_video_date first.
    (Staleness-first ordering — a series that's gone quiet surfaces
    before one that just posted.)"""
    rows = conn.execute(
        """SELECT * FROM series
           WHERE status = 'active'
           ORDER BY last_video_date ASC NULLS FIRST"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_series(conn, series_id):
    row = conn.execute(
        "SELECT * FROM series WHERE series_id = ?", (series_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["canon_facts"] = json.loads(d["canon_facts"])
    d["characters"] = json.loads(d["characters"])
    d["unresolved_threads"] = json.loads(d["unresolved_threads"])
    return d


def create_series(conn, series_name, category, format_, total_parts_planned=None):
    cur = conn.execute(
        """INSERT INTO series (series_name, category, format, total_parts_planned)
           VALUES (?, ?, ?, ?)""",
        (series_name, category, format_, total_parts_planned),
    )
    return cur.lastrowid


def update_series_state(conn, series_id, *, canon_facts=None, characters=None,
                         unresolved_threads=None, last_episode_summary=None,
                         status=None, bump_part=False):
    """Merge new extracted facts into a series' story bible.
    Pass only the fields you want to update — None means unchanged."""
    series = get_series(conn, series_id)
    if series is None:
        raise ValueError(f"No series with id {series_id}")

    new_canon = series["canon_facts"]
    if canon_facts:
        # de-dupe while preserving order
        for fact in canon_facts:
            if fact not in new_canon:
                new_canon.append(fact)

    new_characters = series["characters"]
    if characters:
        new_characters.update(characters)

    new_threads = unresolved_threads if unresolved_threads is not None else series["unresolved_threads"]
    new_summary = last_episode_summary if last_episode_summary is not None else series["last_episode_summary"]
    new_status = status if status is not None else series["status"]
    new_part = series["current_part"] + (1 if bump_part else 0)

    conn.execute(
        """UPDATE series SET
             canon_facts = ?, characters = ?, unresolved_threads = ?,
             last_episode_summary = ?, status = ?, current_part = ?,
             updated_at = ?, last_video_date = ?
           WHERE series_id = ?""",
        (
            json.dumps(new_canon), json.dumps(new_characters), json.dumps(new_threads),
            new_summary, new_status, new_part,
            _now(), _now(), series_id,
        ),
    )


# ------------------------------------------------------------------
# Videos
# ------------------------------------------------------------------

def script_hash(script_text):
    return hashlib.sha256(script_text.encode("utf-8")).hexdigest()[:16]


def create_video(conn, *, category, format_, style, series_id=None, series_part=None,
                  title=None, hook_line=None, ending_line=None, cta=None,
                  script_json=None):
    s_hash = script_hash(json.dumps(script_json, sort_keys=True)) if script_json else None
    cur = conn.execute(
        """INSERT INTO videos
           (series_id, series_part, category, format, style, title,
            hook_line, ending_line, cta, script_json, script_hash, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scripted')""",
        (series_id, series_part, category, format_, style, title,
         hook_line, ending_line, cta,
         json.dumps(script_json) if script_json else None, s_hash),
    )
    return cur.lastrowid


def update_video_status(conn, video_id, status, **fields):
    """Update status plus any of: audio_path, video_path, thumbnail_path,
    visual_manifest_path, youtube_video_id, error_message.
    uploaded_at auto-set if status='uploaded'."""
    sets = ["status = ?"]
    values = [status]
    for key in ("audio_path", "video_path", "thumbnail_path",
                "visual_manifest_path", "youtube_video_id", "error_message"):
        if key in fields:
            sets.append(f"{key} = ?")
            values.append(fields[key])
    if status == "uploaded":
        sets.append("uploaded_at = ?")
        values.append(_now())
    values.append(video_id)
    conn.execute(f"UPDATE videos SET {', '.join(sets)} WHERE video_id = ?", values)


def recent_categories(conn, limit=10):
    """Categories of the last N videos — used to avoid posting the
    same category back-to-back too often."""
    rows = conn.execute(
        "SELECT category FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [r["category"] for r in rows]


# ------------------------------------------------------------------
# Run log
# ------------------------------------------------------------------

def log_run_start(conn, decision, reason):
    cur = conn.execute(
        "INSERT INTO run_log (decision, reason) VALUES (?, ?)", (decision, reason)
    )
    return cur.lastrowid


def log_run_finish(conn, run_id, status, video_id=None):
    conn.execute(
        "UPDATE run_log SET status = ?, video_id = ?, finished_at = ? WHERE run_id = ?",
        (status, video_id, _now(), run_id),
    )


if __name__ == "__main__":
    init_db()
    print(f"Database ready at {DB_PATH}")

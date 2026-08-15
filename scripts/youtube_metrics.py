"""
youtube_metrics.py — lightweight YouTube performance telemetry for Night Loom.

V1 intentionally uses the existing YouTube Data API OAuth credentials so the
hosted worker does not need a new Analytics OAuth consent flow. It captures
cumulative video statistics at maturity checkpoints (24h and 48h) and stores
immutable snapshots in SQLite/Supabase-backed memory.

The learning engine consumes these snapshots; it never mutates a video's
content after publication.
"""

from datetime import datetime, timezone

from . import memory
from . import youtube_uploader

SNAPSHOT_AGES = {
    "24h": 24.0,
    "48h": 48.0,
}


def _parse_uploaded_at(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _existing_snapshots(conn, video_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT snapshot_label FROM video_metrics WHERE video_id = ?",
        (video_id,),
    ).fetchall()
    return {r["snapshot_label"] for r in rows}


def _fetch_stats(service, youtube_ids: list[str]) -> dict[str, dict]:
    stats = {}
    # YouTube Data API accepts up to 50 IDs in one request.
    for start in range(0, len(youtube_ids), 50):
        batch = youtube_ids[start:start + 50]
        response = service.videos().list(
            part="statistics,snippet",
            id=",".join(batch),
        ).execute()
        for item in response.get("items", []):
            raw = item.get("statistics", {})
            stats[item["id"]] = {
                "views": int(raw.get("viewCount", 0)),
                "likes": int(raw.get("likeCount", 0)),
                "comments": int(raw.get("commentCount", 0)),
            }
    return stats


def collect_due_snapshots() -> int:
    """Collect due 24h/48h snapshots for uploaded videos.

    Returns the number of snapshots written. Failures are non-fatal because
    telemetry must never stop the production scheduler.
    """
    now = datetime.now(timezone.utc)

    try:
        service = youtube_uploader.get_authenticated_service(interactive=False)
    except Exception as exc:
        print(f"[metrics] Analytics telemetry unavailable: {exc}")
        return 0

    with memory.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT video_id, youtube_video_id, uploaded_at
            FROM videos
            WHERE status = 'uploaded'
              AND youtube_video_id IS NOT NULL
              AND uploaded_at IS NOT NULL
            ORDER BY video_id ASC
            """
        ).fetchall()

        due = []
        for row in rows:
            uploaded = _parse_uploaded_at(row["uploaded_at"])
            if not uploaded:
                continue
            age_hours = (now - uploaded).total_seconds() / 3600.0
            existing = _existing_snapshots(conn, row["video_id"])
            labels = [label for label, threshold in SNAPSHOT_AGES.items()
                      if age_hours >= threshold and label not in existing]
            if labels:
                due.append((dict(row), age_hours, labels))

        if not due:
            print("[metrics] No due performance snapshots.")
            return 0

        yt_ids = [item[0]["youtube_video_id"] for item in due]
        stats_map = _fetch_stats(service, yt_ids)
        written = 0

        for row, age_hours, labels in due:
            stats = stats_map.get(row["youtube_video_id"])
            if stats is None:
                continue
            for label in labels:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO video_metrics
                    (video_id, youtube_video_id, snapshot_label, age_hours,
                     views, likes, comments, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["video_id"], row["youtube_video_id"], label,
                        round(age_hours, 2), stats["views"], stats["likes"],
                        stats["comments"], now.isoformat(),
                    ),
                )
                written += 1

        if written:
            print(f"[metrics] 📊 Stored {written} performance snapshots.")
        return written


if __name__ == "__main__":
    memory.init_db()
    print(f"Snapshots written: {collect_due_snapshots()}")

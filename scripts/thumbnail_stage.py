"""
thumbnail_stage.py — runs thumbnail generation for pending videos.

Generates high-CTR 1080x1920 SDXL thumbnail art + bold text overlay,
saves to assets/images/video_N_thumbnail.png, and updates SQLite DB.

Usage:
  python -m scripts.thumbnail_stage [--video VIDEO_ID]
"""

import argparse
import sys
from pathlib import Path

from . import memory, thumbnail_generator


def process_video(video_id: int):
    """Generates a thumbnail for a single video by ID and updates DB."""
    with memory.get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        if not row:
            print(f"[thumbnail_stage] video {video_id} not found in DB.")
            return

        video = dict(row)
        title = video.get("title", f"video_{video_id}")

        print(f"[thumbnail_stage] Generating thumbnail for video {video_id}: '{title}' ...")

        try:
            thumb_path = thumbnail_generator.generate(video_id=video_id)
            memory.update_video_status(
                conn,
                video_id=video_id,
                status=video.get("status", "rendered"),
                thumbnail_path=str(thumb_path),
            )
            print(f"[thumbnail_stage] DB updated with thumbnail: {thumb_path.name}")
        except Exception as e:
            print(f"[thumbnail_stage] video {video_id} FAILED: {e}")
            raise


def process_all_pending():
    """Process all videos in DB requiring thumbnails."""
    with memory.get_conn() as conn:
        rows = conn.execute(
            "SELECT video_id FROM videos WHERE thumbnail_path IS NULL OR thumbnail_path = '' ORDER BY video_id ASC"
        ).fetchall()
        vids = [r["video_id"] for r in rows]

    if not vids:
        print("[thumbnail_stage] No pending videos found for thumbnail generation.")
        return

    print(f"[thumbnail_stage] Found {len(vids)} pending video(s): {vids}")
    for vid in vids:
        process_video(vid)


def main():
    parser = argparse.ArgumentParser(description="Thumbnail generation stage")
    parser.add_argument("--video", type=int, default=None, help="Process a specific video ID")
    args = parser.parse_args()

    memory.init_db()

    if args.video:
        process_video(args.video)
    else:
        process_all_pending()


if __name__ == "__main__":
    main()

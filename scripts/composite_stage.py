"""
composite_stage.py — runs video compositing & final assembly for pending videos.

Finds videos whose avatar / visuals stage is complete and renders the final 9:16 Shorts video
with 1080x1920 background timeline, bottom-left circular avatar overlay, and yellow-highlighted karaoke subtitles.

Usage:
  python -m scripts.composite_stage [--video VIDEO_ID]
"""

import argparse
import sys
from pathlib import Path

from . import memory
from .video_composer import compose


def process_video(video_id: int):
    """Composites a single video by ID and updates DB status to 'rendered'."""
    with memory.get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        if not row:
            print(f"[composite_stage] video {video_id} not found in DB.")
            return

        video = dict(row)
        title = video.get("title", f"video_{video_id}")

        print(f"[composite_stage] Compositing video {video_id}: '{title}' (status: {video.get('status')}) ...")

        try:
            out_video_path = compose(video_id=video_id)
            memory.update_video_status(
                conn,
                video_id=video_id,
                status="rendered",
                video_path=str(out_video_path),
            )
            print(f"[composite_stage] Manifest & DB updated to 'rendered'.")
            print(f"[composite_stage] video {video_id} -> final output ready: {out_video_path.name}")
        except Exception as e:
            memory.update_video_status(
                conn,
                video_id=video_id,
                status="failed",
                error_message=str(e),
            )
            print(f"[composite_stage] video {video_id} FAILED: {e}")
            raise


def process_all_pending():
    """Process all videos in DB ready for compositing."""
    with memory.get_conn() as conn:
        rows = conn.execute(
            "SELECT video_id FROM videos WHERE status IN ('avatar_ready', 'visualized', 'voiced') ORDER BY video_id ASC"
        ).fetchall()
        vids = [r["video_id"] for r in rows]

    if not vids:
        print("[composite_stage] No pending videos found for compositing.")
        return

    print(f"[composite_stage] Found {len(vids)} pending video(s): {vids}")
    for vid in vids:
        process_video(vid)


def main():
    parser = argparse.ArgumentParser(description="Video compositing & assembly stage")
    parser.add_argument("--video", type=int, default=None, help="Process a specific video ID")
    args = parser.parse_args()

    memory.init_db()

    if args.video:
        process_video(args.video)
    else:
        process_all_pending()


if __name__ == "__main__":
    main()

"""
upload_stage.py — runs LLM metadata optimization & YouTube uploading for rendered videos.

Usage:
  python -m scripts.upload_stage [--video VIDEO_ID] [--privacy {private,unlisted,public}]
"""

import argparse
import sys
from pathlib import Path

from . import memory, metadata_optimizer, youtube_uploader


def process_video(video_id: int, privacy: str = "private"):
    """Generates AI metadata, uploads video & thumbnail to YouTube, and updates DB."""
    with memory.get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        if not row:
            print(f"[upload_stage] video {video_id} not found in DB.")
            return

        video = dict(row)
        title = video.get("title", f"video_{video_id}")
        video_path = video.get("video_path")
        thumbnail_path = video.get("thumbnail_path")

        if not video_path or not Path(video_path).exists():
            print(f"[upload_stage] Rendered video file missing for video {video_id}: {video_path}")
            return

        print(f"[upload_stage] Uploading video {video_id}: '{title}' (privacy: {privacy}) ...")

        try:
            # 1. Generate LLM YouTube Algorithm Metadata
            metadata = metadata_optimizer.generate_metadata(video_id=video_id)

            # 2. Upload to YouTube via API v3
            yt_id = youtube_uploader.upload_video(
                video_file_path=video_path,
                thumbnail_path=thumbnail_path,
                metadata=metadata,
                privacy_status=privacy,
            )

            # 3. Update SQLite DB to 'uploaded'
            memory.update_video_status(
                conn,
                video_id=video_id,
                status="uploaded",
                youtube_video_id=yt_id,
            )
            print(f"[upload_stage] DB updated with youtube_video_id: {yt_id} (status: uploaded)")
        except Exception as e:
            memory.update_video_status(
                conn,
                video_id=video_id,
                status=video.get("status", "rendered"),
                error_message=str(e),
            )
            print(f"[upload_stage] video {video_id} FAILED: {e}")
            raise


def process_all_pending(privacy: str = "private"):
    """Upload all rendered videos in DB."""
    with memory.get_conn() as conn:
        rows = conn.execute(
            "SELECT video_id FROM videos WHERE status = 'rendered' ORDER BY video_id ASC"
        ).fetchall()
        vids = [r["video_id"] for r in rows]

    if not vids:
        print("[upload_stage] No rendered videos pending upload.")
        return

    print(f"[upload_stage] Found {len(vids)} video(s) ready for upload: {vids}")
    for vid in vids:
        process_video(vid, privacy=privacy)


def main():
    parser = argparse.ArgumentParser(description="YouTube metadata optimization & auto-upload stage")
    parser.add_argument("--video", type=int, default=None, help="Process a specific video ID")
    parser.add_argument("--privacy", type=str, default="private", choices=["private", "unlisted", "public"], help="YouTube privacy status")
    args = parser.parse_args()

    memory.init_db()

    if args.video:
        process_video(args.video, privacy=args.privacy)
    else:
        process_all_pending(privacy=args.privacy)


if __name__ == "__main__":
    main()

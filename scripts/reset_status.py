"""
reset_status.py — resets failed videos back to 'visualized' (or specified status)
so stages can be re-run easily during testing.

Usage:
    python -m scripts.reset_status
    python -m scripts.reset_status --to voiced
"""

import sys
from . import memory as mem

def reset_video(video_id=None, target_status="visualized"):
    mem.init_db()
    with mem.get_conn() as conn:
        if video_id is not None:
            rows = conn.execute("SELECT video_id, title, status FROM videos WHERE video_id = ?", (video_id,)).fetchall()
        else:
            rows = conn.execute("SELECT video_id, title, status FROM videos WHERE status = 'failed'").fetchall()

        if not rows:
            print("[reset_status] No matching videos found.")
            return

        print(f"[reset_status] Resetting {len(rows)} video(s) to '{target_status}':")
        for r in rows:
            print(f"  video {r['video_id']}: {r['title']} ({r['status']} -> {target_status})")
            conn.execute(
                "UPDATE videos SET status = ?, error_message = NULL WHERE video_id = ?",
                (target_status, r["video_id"])
            )
        print("[reset_status] Done.")

if __name__ == "__main__":
    to = "visualized"
    vid = None
    if "--to" in sys.argv:
        idx = sys.argv.index("--to")
        to = sys.argv[idx + 1]
    if "--video" in sys.argv:
        idx = sys.argv.index("--video")
        vid = int(sys.argv[idx + 1])
    reset_video(video_id=vid, target_status=to)

"""
avatar_stage.py — picks up every video in 'visualized' status, generates
a lip-synced presenter avatar clip via Wav2Lip, and writes the clip path
back into the visual manifest so the assembly stage can overlay it.

Status flow:
    visualized  →  (avatar generated)  →  manifest updated
    (status stays 'visualized' — assembly is the stage that advances it)

Usage:
    python -m scripts.avatar_stage
    python -m scripts.avatar_stage --video 1   # process a specific video
"""

import json
import sys
from pathlib import Path

from . import config
from . import memory as mem
from . import avatar_generator


def _update_manifest_overlay(video_id, avatar_path):
    """Patch overlay_avatar in the visual manifest with the generated clip path."""
    manifest_path = config.ASSETS_DIR / "visuals" / f"video_{video_id}_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Visual manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    manifest["overlay_avatar"]["enabled"] = True
    manifest["overlay_avatar"]["asset_path"] = str(avatar_path)
    # Layout defaults are set in visuals_planner; keep them unless overridden
    manifest["overlay_avatar"].setdefault("layout", "pip_bottom_right")
    manifest["overlay_avatar"].setdefault("crop_shape", "circle")

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[avatar_stage] Manifest updated: {manifest_path.name}")


def process_video(video_id):
    """Generate avatar overlay for a single video and update its manifest."""
    mem.init_db()
    with mem.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()

    if row is None:
        raise ValueError(f"No video with id {video_id}")
    if row["status"] not in ("visualized", "voiced"):
        print(
            f"[avatar_stage] video {video_id} is in status '{row['status']}' "
            f"(expected 'visualized' or 'voiced') — skipping."
        )
        return

    try:
        avatar_path = avatar_generator.generate(video_id=video_id)
        _update_manifest_overlay(video_id, avatar_path)
        print(f"[avatar_stage] video {video_id} -> avatar overlay ready.")
    except Exception as e:
        with mem.get_conn() as conn:
            mem.update_video_status(conn, video_id, "failed", error_message=str(e))
        print(f"[avatar_stage] video {video_id} FAILED: {e}")
        raise


def process_all_pending():
    """Process every video currently in 'visualized' status."""
    mem.init_db()
    with mem.get_conn() as conn:
        rows = conn.execute(
            "SELECT video_id FROM videos WHERE status = 'visualized'"
        ).fetchall()
        video_ids = [r["video_id"] for r in rows]

    if not video_ids:
        print("[avatar_stage] No visualized videos pending avatar generation.")
        return

    print(f"[avatar_stage] Processing {len(video_ids)} pending video(s): {video_ids}")
    for vid in video_ids:
        process_video(vid)


if __name__ == "__main__":
    if "--video" in sys.argv:
        idx = sys.argv.index("--video")
        vid = int(sys.argv[idx + 1])
        process_video(vid)
    else:
        process_all_pending()

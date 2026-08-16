"""
visuals_stage.py — picks up every video in 'voiced' status and runs the
full visual pipeline:

  1. Build a timed shot list (visuals_planner)
  2. Generate / fetch background assets (sdxl_generator or pexels_client)
  3. Write video_N_manifest.json to assets/visuals/
  4. Advance DB status to 'visualized'

Avatar overlay (Wav2Lip) is a future stage; we reserve its slot in the
manifest now so the assembly stage can key off it later.

Usage:
    python -m scripts.visuals_stage
    python -m scripts.visuals_stage --style sdxl   # force style A
    python -m scripts.visuals_stage --style pexels  # force style B
"""

import json
import sys
from pathlib import Path

from . import memory as mem
from . import config
from . import visuals_planner


# Map the DB style column (A / B) to an internal key used throughout visuals
_STYLE_MAP = {
    "A": "sdxl",
    "B": "pexels",
    # C is no longer a separate style — avatar is an overlay on A or B
}


def _format_from_row(row):
    return "short" if row["format"] == "short" else "long"


def process_video(video_id, conn=None, style_override=None):
    if conn is None:
        with mem.get_conn() as c:
            return process_video(video_id, conn=c, style_override=style_override)

    row = conn.execute(
        "SELECT * FROM videos WHERE video_id = ?", (video_id,)
    ).fetchone()

    if row is None:
        raise ValueError(f"No video with id {video_id}")
    if row["status"] != "voiced":
        print(
            f"[visuals_stage] video {video_id} is in status '{row['status']}', "
            f"not 'voiced' — skipping."
        )
        return

    # Resolve background style
    db_style = row["style"] if row["style"] in _STYLE_MAP else "A"
    background_style = style_override or _STYLE_MAP.get(db_style, "sdxl")
    format_ = _format_from_row(row)

    # Avatar overlay is enabled by default for style A & B; can be toggled
    avatar_enabled = True   # TODO: drive from DB/config when wav2lip is ready

    # ------------------------------------------------------------------ #
    # 1. Build the shot plan                                               #
    # ------------------------------------------------------------------ #
    script_json = json.loads(row["script_json"])
    ts_path = config.ASSETS_DIR / "audio" / f"video_{video_id}_timestamps.json"
    if not ts_path.exists():
        raise FileNotFoundError(
            f"Timestamps file not found: {ts_path}. "
            f"Run voice_stage first."
        )
    with open(ts_path) as f:
        timestamps = json.load(f)

    print(f"[visuals_stage] Planning shots for video {video_id} (style={background_style})...")
    plan, plan_path = visuals_planner.build_visual_plan(
        video_id=video_id,
        script_json=script_json,
        timestamps=timestamps,
        background_style=background_style,
        avatar_enabled=avatar_enabled,
    )
    shots = plan["shots"]
    print(f"[visuals_stage]   {len(shots)} shots planned.")

    # ------------------------------------------------------------------ #
    # 2. Generate / fetch background assets                               #
    # ------------------------------------------------------------------ #
    print(f"[visuals_stage] Fetching backgrounds via '{background_style}'...")
    if background_style == "sdxl":
        from . import sdxl_generator
        asset_results = sdxl_generator.generate_shots(shots, video_id, format_=format_)
    elif background_style == "pexels":
        from . import pexels_client
        asset_results = pexels_client.fetch_shots(shots, video_id, format_=format_)
    else:
        raise ValueError(f"Unknown background_style: {background_style!r}")

    # Merge asset paths back into the plan shots
    asset_by_id = {r["shot_id"]: r for r in asset_results}
    for shot in shots:
        merged = asset_by_id.get(shot["shot_id"], {})
        shot["bg_asset_path"] = merged.get("asset_path")
        shot["bg_asset_type"] = merged.get("asset_type")

    manifest = {
        "video_id": video_id,
        "background_style": background_style,
        "format": format_,
        "category": row["category"] if row["category"] else None,   # used by video_composer for BGM selection
        "avatar_enabled": True,
        "shots": shots,
        "overlay_avatar": {
            "enabled": True,
            "layout": "pip_bottom_left",
            "crop_shape": "circle",
        },
    }

    manifest_dir = config.ASSETS_DIR / "visuals"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"video_{video_id}_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    mem.update_video_status(
        conn, video_id, "visualized", visual_manifest_path=str(manifest_path)
    )
    print(f"[visuals_stage] Manifest written: {manifest_path.name}")
    print(f"[visuals_stage] video {video_id} -> status 'visualized'.")


def process_all_pending(style_override=None):
    """Process all videos in DB ready for visual generation."""
    with mem.get_conn() as conn:
        rows = conn.execute(
            "SELECT video_id FROM videos WHERE status = 'voiced'"
        ).fetchall()
        video_ids = [r["video_id"] for r in rows]

    if not video_ids:
        print("[visuals_stage] No videos pending visual generation.")
        return

    print(f"[visuals_stage] Processing {len(video_ids)} pending video(s): {video_ids}")
    for vid in video_ids:
        with mem.get_conn() as conn:
            try:
                process_video(vid, conn=conn, style_override=style_override)
            except Exception as e:
                mem.update_video_status(conn, vid, "failed", error_message=str(e))
                print(f"[visuals_stage] video {vid} FAILED: {e}")
                raise


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Visuals generation stage")
    parser.add_argument("--video", type=int, default=None, help="Process a specific video ID")
    parser.add_argument("--style", type=str, default=None, choices=["sdxl", "pexels"], help="Override background style")
    args = parser.parse_args()

    mem.init_db()
    if args.video:
        process_video(args.video, style_override=args.style)
    else:
        process_all_pending(style_override=args.style)


if __name__ == "__main__":
    main()

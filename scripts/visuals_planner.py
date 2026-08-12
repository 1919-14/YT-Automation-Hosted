"""
visuals_planner.py — given a voiced video's script + segment timestamps,
produces a structured shot list that both the SDXL generator and the
Pexels client can consume.

Output (returned dict, also written to assets/visuals/video_N_plan.json):
{
  "video_id": N,
  "background_style": "sdxl" | "pexels",
  "avatar_enabled": bool,
  "shots": [
    {
      "shot_id": 1,
      "start_time": 0.0,
      "end_time": 3.86,
      "duration": 3.86,
      "bg_prompt": "...",    # for SDXL
      "pexels_query": "...", # for Pexels
      "segment_text": "..."  # original narration text for reference
    },
    ...
  ]
}

The planner never touches VRAM or the network — it's pure data transformation.
"""

import json
import re
from pathlib import Path

from . import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify_to_query(text, max_words=5):
    """Turn a visual_prompt or narration snippet into a concise Pexels query.
    Strips filler words, keeps the most concrete nouns / adjectives."""
    STOPWORDS = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "i", "me", "my", "he", "she", "they", "we", "it", "his", "her",
        "this", "that", "so", "then", "by", "as", "up", "out", "can",
        "who", "which", "what", "when", "where", "how", "not", "no",
    }
    words = re.sub(r"[^a-zA-Z0-9 ]", "", text.lower()).split()
    filtered = [w for w in words if w not in STOPWORDS]
    return " ".join(filtered[:max_words])


def _build_shot_from_segment(shot_id, segment, visual_prompt=None):
    """
    segment: one entry from timestamps.json
      {"text": str, "start": float, "end": float, "words": [...]}
    visual_prompt: optional override from script_json scene (more descriptive)
    """
    start = segment.get("start") or 0.0
    end = segment.get("end") or start

    # Prefer the LLM-written visual_prompt if available (richer for SDXL);
    # fall back to deriving a query from the spoken narration text.
    base_text = visual_prompt or segment["text"]
    pexels_q = _slugify_to_query(base_text)
    sdxl_prompt = (
        visual_prompt
        if visual_prompt
        else f"cinematic still: {segment['text'][:120]}"
    )

    return {
        "shot_id": shot_id,
        "start_time": round(start, 3),
        "end_time": round(end, 3),
        "duration": round(end - start, 3),
        "bg_prompt": sdxl_prompt,
        "pexels_query": pexels_q,
        "segment_text": segment["text"],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_visual_plan(video_id, script_json, timestamps, background_style, avatar_enabled):
    """
    video_id:         int
    script_json:      dict — parsed script from DB
    timestamps:       list — output of captions.transcribe_with_timestamps, after
                      segment mapping (list of {text, start, end, words})
    background_style: "sdxl" | "pexels"
    avatar_enabled:   bool

    Returns the plan dict and also saves it to
    assets/visuals/video_N_plan.json.
    """
    # Build a map from segment text → visual_prompt from script scenes
    scene_prompt_map = {}
    for scene in script_json.get("scenes", []):
        narration = scene.get("narration", "")
        vp = scene.get("visual_prompt", "")
        if narration and vp:
            scene_prompt_map[narration] = vp

    shots = []
    for i, seg in enumerate(timestamps, start=1):
        if seg.get("start") is None:
            continue  # skip empty/unmapped segments
        vp = scene_prompt_map.get(seg["text"])  # may be None for hook/ending/cta
        shots.append(_build_shot_from_segment(i, seg, visual_prompt=vp))

    plan = {
        "video_id": video_id,
        "background_style": background_style,
        "avatar_enabled": avatar_enabled,
        "shots": shots,
        # Avatar overlay section — populated later by wav2lip stage
        "overlay_avatar": {
            "enabled": avatar_enabled,
            "asset_path": None,
            "layout": "pip_bottom_right",  # pip_bottom_right | fullscreen_cutaway
        },
    }

    out_dir = config.ASSETS_DIR / "visuals"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"video_{video_id}_plan.json"
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=2)

    return plan, plan_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.visuals_planner <video_id>")
        sys.exit(1)

    from scripts import memory as mem
    vid = int(sys.argv[1])
    mem.init_db()
    with mem.get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE video_id=?", (vid,)).fetchone()

    script = json.loads(row["script_json"])
    ts_path = config.ASSETS_DIR / "audio" / f"video_{vid}_timestamps.json"
    timestamps = json.load(open(ts_path))

    plan, path = build_visual_plan(
        video_id=vid,
        script_json=script,
        timestamps=timestamps,
        background_style="sdxl",
        avatar_enabled=True,
    )
    print(f"Plan written to {path}")
    print(f"  {len(plan['shots'])} shots planned")
    for s in plan["shots"][:3]:
        print(f"  [{s['start_time']} -> {s['end_time']}s] {s['bg_prompt'][:60]}...")

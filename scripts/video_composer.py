"""
video_composer.py — composites background visual shots, narration audio,
bottom-left circular avatar overlay, and karaoke-style subtitles into a
final 1080x1920 YouTube Short video.

Inputs:
  - assets/visuals/video_N_manifest.json — background shots & timestamps
  - assets/audio/video_N_timestamps.json — word-level Whisper timestamps
  - assets/video/video_N_avatar.mp4      — SadTalker avatar clip with synced audio

Output:
  - output/video_N.mp4                    — final rendered 9:16 Short (1080x1920)
"""

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

from . import config

# ── BGM Track Picker ───────────────────────────────────────────────────────────

# Map content categories → BGM subfolder
_CATEGORY_TO_BGM_FOLDER = {
    "horror":      "horror",
    "mystery":     "horror",       # mystery also uses dark atmospheric tracks
    "facts":       "mystery_facts",
    "motivational":"mystery_facts", # fallback — motivational is banned but keep safe
}
_BGM_BASE = config.ASSETS_DIR / "audio" / "bg_music"


def _pick_bgm_track(category: str | None) -> Path | None:
    """Returns a random .mp3 file path from the appropriate BGM subfolder,
    or None if the folder is empty / missing (graceful no-BGM fallback)."""
    folder_name = _CATEGORY_TO_BGM_FOLDER.get(category or "", "horror")
    folder = _BGM_BASE / folder_name
    if not folder.exists():
        print(f"[video_composer] BGM folder not found: {folder} — skipping BGM.")
        return None
    tracks = list(folder.glob("*.mp3"))
    if not tracks:
        print(f"[video_composer] No .mp3 files in {folder} — skipping BGM.")
        return None
    chosen = random.choice(tracks)
    print(f"[video_composer] BGM track selected: {chosen.name} (folder: {folder_name})")
    return chosen


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_ass_time(seconds: float) -> str:
    """Format seconds (float) to ASS timestamp format: H:MM:SS.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_karaoke_ass(timestamps_path: Path, ass_out_path: Path):
    """
    Generates an ASS subtitle file with karaoke word highlighting:
      - Full sentence shown in bright White (&H00FFFFFF&) with black border.
      - Currently spoken word highlighted in vibrant Yellow (&H0000FFFF&).
      - Positioned in lower-middle area above bottom-left avatar.
    """
    with open(timestamps_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,48,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,60,60,580,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines = []

    for seg in segments:
        words = seg.get("words", [])
        if not words:
            continue

        for i, curr_w in enumerate(words):
            w_start = _format_ass_time(curr_w["start"])
            w_end   = _format_ass_time(curr_w["end"])

            # Build line where curr_w is highlighted in Yellow
            line_parts = []
            for j, w in enumerate(words):
                w_str = w["word"].strip()
                if j == i:
                    line_parts.append(f"{{\\c&H0000FFFF&}}{w_str}{{\\c&H00FFFFFF&}}")
                else:
                    line_parts.append(w_str)

            text_line = " ".join(line_parts)
            dialogue_lines.append(
                f"Dialogue: 0,{w_start},{w_end},Karaoke,,0,0,0,,{text_line}"
            )

    ass_out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ass_out_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(dialogue_lines) + "\n")

    print(f"[video_composer] ASS Karaoke subtitles written to {ass_out_path.name}")


def _get_ffmpeg_cmd():
    """Locate ffmpeg executable."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_bin_dir = Path(exe).parent
        alias_ffmpeg = ffmpeg_bin_dir / "ffmpeg.exe"
        if alias_ffmpeg.exists():
            return str(alias_ffmpeg)
        return exe
    except Exception:
        return "ffmpeg"


# ── Core Compositor ────────────────────────────────────────────────────────────

def compose(video_id: int) -> Path:
    """
    Composites video N:
      1. Sequences background images to 1080x1920 vertical format.
      2. Overlays video_N_avatar.mp4 in bottom-left corner with circular mask (420x420).
      3. Mixes narration audio (100% vol) with atmospheric BGM bed (12% vol, fade in/out).
      4. Burns in karaoke subtitles (sentence white, spoken word yellow).
    """
    manifest_path = config.ASSETS_DIR / "visuals" / f"video_{video_id}_manifest.json"
    timestamps_path = config.ASSETS_DIR / "audio" / f"video_{video_id}_timestamps.json"
    avatar_path = config.ASSETS_DIR / "video" / f"video_{video_id}_avatar.mp4"
    ass_path = config.ASSETS_DIR / "visuals" / f"video_{video_id}_subtitles.ass"

    out_dir = config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_video_path = out_dir / f"video_{video_id}.mp4"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Visual manifest not found: {manifest_path}")
    if not avatar_path.exists():
        raise FileNotFoundError(f"Avatar clip not found: {avatar_path}")
    if not timestamps_path.exists():
        raise FileNotFoundError(f"Timestamps file not found: {timestamps_path}")

    # 1. Generate Karaoke ASS Subtitles
    generate_karaoke_ass(timestamps_path, ass_path)

    # 2. Read manifest
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    shots = manifest.get("shots", [])
    if not shots:
        raise ValueError(f"Manifest {manifest_path} contains no shots.")

    # 3. Create temp concatenation script & intermediate background video
    tmp_dir = config.PROJECT_ROOT / "temp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    bg_video_path = tmp_dir / f"bg_video_{video_id}.mp4"

    ffmpeg_bin = _get_ffmpeg_cmd()

    if bg_video_path.exists() and bg_video_path.stat().st_size > 0:
        print(f"[video_composer] Background video already compiled, reusing: {bg_video_path.name}")
    else:
        print(f"[video_composer] Building 1080x1920 background timeline from {len(shots)} shots ...")

        # Get total duration of avatar video/audio to ensure seamless alignment
        total_audio_duration = 66.0
        try:
            import cv2
            cap = cv2.VideoCapture(str(avatar_path))
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                if fps > 0 and frames > 0:
                    total_audio_duration = frames / fps
            cap.release()
        except Exception:
            try:
                cmd = [ffmpeg_bin, "-i", str(avatar_path)]
                res = subprocess.run(cmd, capture_output=True, text=True)
                import re
                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
                if m:
                    h, m_m, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
                    total_audio_duration = h * 3600 + m_m * 60 + s
            except Exception:
                pass


        input_args = []
        filter_complex = []

        for i, shot in enumerate(shots):
            img_path = shot["bg_asset_path"]
            start_t = shot["start_time"]

            if i < len(shots) - 1:
                next_start = shots[i+1]["start_time"]
                duration = max(0.5, round(next_start - start_t, 2))
            else:
                duration = max(0.5, round(total_audio_duration - start_t, 2))

            if Path(img_path).suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]:
                input_args.extend([
                    "-stream_loop", "-1",
                    "-t", str(duration),
                    "-i", str(img_path)
                ])
            else:
                input_args.extend([
                    "-loop", "1",
                    "-t", str(duration),
                    "-i", str(img_path)
                ])

            filter_complex.append(
                f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1,fps=30[v{i}];"
            )

        concat_inputs = "".join(f"[v{i}]" for i in range(len(shots)))
        filter_complex.append(f"{concat_inputs}concat=n={len(shots)}:v=1:a=0[bg_v]")

        filter_str = "".join(filter_complex)

        bg_cmd = [
            ffmpeg_bin, "-y",
            *input_args,
            "-filter_complex", filter_str,
            "-map", "[bg_v]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(bg_video_path)
        ]

        subprocess.check_call(bg_cmd)
        print(f"[video_composer] Background video compiled: {bg_video_path.name}")

    # 4. Composite Avatar Overlay (Bottom-Left Circular Badge) + Subtitles + Audio
    print(f"[video_composer] Compositing bottom-left circular avatar badge & karaoke subtitles ...")

    # Pick BGM track based on manifest category (graceful no-BGM fallback if missing)
    content_category = manifest.get("category", None)
    bgm_track = _pick_bgm_track(content_category)

    # Escaped ASS path for ffmpeg filter syntax (Windows backslashes need escaping)
    ass_path_str = str(ass_path).replace("\\", "/").replace(":", "\\:")

    # Avatar Overlay Filter:
    #   [1:v] avatar video -> scaled to 420x420, cropped into a smooth circle using geq alpha mask
    #   Overlay at x=40, y=1920-420-120 = 1380 (bottom-left)
    #   Subtitles burned in over background+overlay
    comp_filter = (
        f"[1:v]scale=420:420,format=rgba,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(hypot(X-210,Y-210),206),255,0)'[avatar_circular];"
        f"[0:v][avatar_circular]overlay=40:1380:shortest=1[v_overlay];"
        f"[v_overlay]ass='{ass_path_str}'[v_out]"
    )

    if bgm_track:
        # BGM mixed at 12% volume with 1.0s fade-in and 1.5s fade-out.
        # Narration (from avatar) stays at 100% as the lead audio.
        #
        # FIX: Use amix=duration=first so the mix always follows the
        # narration length — NOT the BGM length. This prevents the short
        # BGM clip from cutting the video off early.
        # -stream_loop -1 on the BGM input loops it if the video is longer
        # than the track (handles all track lengths gracefully).
        # -shortest is NOT used here — amix=first already terminates correctly.
        afade_out_start = max(0.0, total_audio_duration - 1.5)
        audio_filter = (
            f"[1:a]volume=1.0[narration];"
            f"[2:a]volume=0.12,afade=t=in:st=0:d=1.0,afade=t=out:st={afade_out_start:.2f}:d=1.5[bgm];"
            f"[narration][bgm]amix=inputs=2:duration=first:normalize=0[audio_out]"
        )
        final_cmd = [
            ffmpeg_bin, "-y",
            "-i", str(bg_video_path),
            "-i", str(avatar_path),
            "-stream_loop", "-1",              # loop BGM so it's never shorter than the video
            "-i", str(bgm_track),              # Input 2: BGM track
            "-filter_complex", comp_filter + ";" + audio_filter,
            "-map", "[v_out]",
            "-map", "[audio_out]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            str(out_video_path)
        ]
        print(f"[video_composer] Mixing BGM at 12% volume: {bgm_track.name} (afade-out at {afade_out_start:.2f}s)")

    else:
        # No BGM available — passthrough narration only
        final_cmd = [
            ffmpeg_bin, "-y",
            "-i", str(bg_video_path),
            "-i", str(avatar_path),
            "-filter_complex", comp_filter,
            "-map", "[v_out]",
            "-map", "1:a",                  # Direct audio passthrough from avatar video
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(out_video_path)
        ]
        print(f"[video_composer] No BGM — using narration audio only.")

    subprocess.check_call(final_cmd)
    print(f"[video_composer] FINAL SHORTS VIDEO GENERATED: {out_video_path}")

    # Cleanup temp bg video
    bg_video_path.unlink(missing_ok=True)

    return out_video_path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        compose(int(sys.argv[1]))
    else:
        compose(1)

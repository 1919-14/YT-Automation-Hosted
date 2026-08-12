"""
avatar_generator.py — generates an expressive talking-head avatar video using
SadTalker (audio-driven portrait animation).

SadTalker produces natural head motion, eye blinks, and facial expressions
directly from the narration audio — no template video needed.

Input:
  - assets/templates/avatar_base.png  — presenter portrait (single image)
  - assets/audio/video_N.mp3          — narration audio

Output:
  - assets/video/video_N_avatar.mp4   — animated talking-head clip

Usage:
    from scripts import avatar_generator
    avatar_generator.generate(video_id=1)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config
from .sadtalker_setup import ensure_sadtalker

# ── Constants ──────────────────────────────────────────────────────────────────

AVATAR_BASE = config.ASSETS_DIR / "templates" / "avatar_base.png"

# SadTalker rendering size: 256 (faster, VRAM-safe) or 512 (higher VRAM)
SADTALKER_SIZE = 256

# Enable GFPGAN face enhancer (False by default for fast VRAM-safe generation)
USE_ENHANCER = False

# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_avatar_face(custom_path=None):
    """Find the avatar base image. Only PNG/JPG — SadTalker takes a still image."""
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"Custom avatar face path not found: {custom_path}")

    templates_dir = config.ASSETS_DIR / "templates"
    for ext in [".png", ".jpg", ".jpeg"]:
        candidate = templates_dir / f"avatar_base{ext}"
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"No avatar base template found in {templates_dir}.\n"
        f"Place a portrait PNG at assets/templates/avatar_base.png"
    )


def _mp3_to_wav(mp3_path: Path, wav_path: Path):
    """Convert MP3 to WAV using the bundled imageio-ffmpeg binary."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        ffmpeg_exe = "ffmpeg"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(mp3_path),
        "-ar", "16000",
        "-ac", "1",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg mp3→wav conversion failed:\n{result.stderr.decode()}"
        )


def _generate_static_avatar_clip(face_path: Path, audio_mp3: Path, out_path: Path):
    """Generates a static avatar clip with narration audio using FFmpeg (zero GPU needed, runs in 1s)."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_exe = "ffmpeg"

    cmd = [
        ffmpeg_exe, "-y",
        "-loop", "1",
        "-i", str(face_path),
        "-i", str(audio_mp3),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(out_path),
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"Static avatar FFmpeg generation failed: {res.stderr.decode()}")
    print(f"[avatar] Static avatar clip generated with FFmpeg (CPU-safe): {out_path.name}")
    return out_path


# ── Public API ─────────────────────────────────────────────────────────────────

def generate(video_id, avatar_base_path=None, use_enhancer=None):
    """
    Generate an expressive talking-head avatar clip for a given video.

    video_id:         int
    avatar_base_path: Path | None — override default avatar_base.png
    use_enhancer:     bool | None — override USE_ENHANCER constant

    Returns the output Path of the generated avatar clip.
    """
    audio_mp3  = config.ASSETS_DIR / "audio"  / f"video_{video_id}.mp3"
    face_path  = _resolve_avatar_face(avatar_base_path)
    out_dir    = config.ASSETS_DIR / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path   = out_dir / f"video_{video_id}_avatar.mp4"

    # Instant asset reuse: skip if avatar clip is already generated
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"[avatar] Avatar clip already exists, reusing: {out_path.name}")
        return out_path

    if not audio_mp3.exists():
        raise FileNotFoundError(f"Narration audio not found: {audio_mp3}")

    # Check for GPU / CPU mode
    use_animated = os.getenv("ENABLE_ANIMATED_AVATAR", "auto").lower()
    has_gpu = False
    try:
        import torch
        has_gpu = torch.cuda.is_available()
    except Exception:
        has_gpu = False

    if use_animated == "false" or (use_animated == "auto" and not has_gpu):
        print(f"[avatar] No GPU detected (or static mode) — using fast CPU image presenter overlay...")
        return _generate_static_avatar_clip(face_path, audio_mp3, out_path)

    enhance = USE_ENHANCER if use_enhancer is None else use_enhancer

    # ── 1. Ensure SadTalker is ready ──────────────────────────────────────────
    try:
        sadtalker_dir = ensure_sadtalker()
    except Exception as e:
        print(f"[avatar] SadTalker setup failed ({e}) — using static image presenter...")
        return _generate_static_avatar_clip(face_path, audio_mp3, out_path)



    # ── 2. Prepare ffmpeg in PATH ─────────────────────────────────────────────
    env = os.environ.copy()
    try:
        import imageio_ffmpeg
        ffmpeg_exe_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
        ffmpeg_bin_dir = ffmpeg_exe_path.parent
        alias_ffmpeg = ffmpeg_bin_dir / "ffmpeg.exe"
        if not alias_ffmpeg.exists():
            shutil.copy2(ffmpeg_exe_path, alias_ffmpeg)
        env["PATH"] = str(ffmpeg_bin_dir) + os.pathsep + env.get("PATH", "")
    except Exception as e:
        print(f"[avatar] Warning: Could not set up ffmpeg.exe alias: {e}")

    # ── 3. Convert mp3 → wav ──────────────────────────────────────────────────
    tmp_dir  = sadtalker_dir / "tmp_audio"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    wav_path = tmp_dir / f"video_{video_id}.wav"

    if not wav_path.exists():
        print(f"[avatar] Converting audio to WAV ...")
        _mp3_to_wav(audio_mp3, wav_path)

    # ── 4. Set up result dir for SadTalker output ─────────────────────────────
    result_dir = sadtalker_dir / "results" / f"video_{video_id}"
    result_dir.mkdir(parents=True, exist_ok=True)

    print(f"[avatar] Generating expressive avatar for video {video_id} ...")
    print(f"  face      : {face_path}")
    print(f"  audio     : {wav_path}")
    print(f"  size      : {SADTALKER_SIZE}px")
    print(f"  enhancer  : {'gfpgan' if enhance else 'none'}")
    print(f"  output    : {out_path}")

    # ── 5. Build SadTalker inference command ──────────────────────────────────
    cmd = [
        sys.executable,
        str(sadtalker_dir / "inference.py"),
        "--driven_audio",  str(wav_path),
        "--source_image",  str(face_path),
        "--result_dir",    str(result_dir),
        "--preprocess",    "crop",
        "--size",          str(SADTALKER_SIZE),
        "--batch_size",    "2",
        "--still",                             # subtle head motion (no wild movement)
        "--expression_scale", "1.0",           # 1.0 = natural, >1 = exaggerated
    ]

    if enhance:
        cmd += ["--enhancer", "gfpgan"]

    # ── 6. Run inference ──────────────────────────────────────────────────────
    try:
        print(f"[avatar] Running SadTalker inference ...")
        result = subprocess.run(
            cmd,
            cwd=str(sadtalker_dir),
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"SadTalker inference failed with exit code {result.returncode}."
            )

        # ── 7. Move output to canonical path ─────────────────────────────────────
        candidates = sorted(result_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise RuntimeError(
                f"SadTalker did not produce any .mp4 output in {result_dir}"
            )
        generated = candidates[-1]   # most recent
        shutil.move(str(generated), str(out_path))

        print(f"[avatar] Expressive avatar clip saved: {out_path}")
        return out_path
    except Exception as e:
        print(f"[avatar] SadTalker failed ({e}) — falling back to static presenter image clip...")
        return _generate_static_avatar_clip(face_path, audio_mp3, out_path)



if __name__ == "__main__":
    vid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    generate(video_id=vid)

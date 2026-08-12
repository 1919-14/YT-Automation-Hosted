"""
thumbnail_generator.py — generates high-CTR 1080x1920 YouTube Short thumbnails.

Combines:
  1. Video Frame Extraction (from rendered final video via FFmpeg) OR SDXL/background image.
  2. High-impact bold text hook overlay (Yellow & White typography with heavy dark strokes).
  3. Circular NightLoom channel logo badge with crisp white border ring.

Outputs:
  - assets/images/video_N_thumbnail.png
"""

import math
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config


def _get_ffmpeg():
    """Locate ffmpeg executable."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _extract_frame_from_video(video_path: Path, out_image_path: Path, timestamp_sec: float = 2.0) -> bool:
    """Extracts a single crisp frame from the rendered MP4 using FFmpeg."""
    if not video_path.exists():
        return False
    try:
        ffmpeg_bin = _get_ffmpeg()
        cmd = [
            ffmpeg_bin, "-y",
            "-ss", str(timestamp_sec),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(out_image_path),
        ]
        res = subprocess.run(cmd, capture_output=True)
        return res.returncode == 0 and out_image_path.exists() and out_image_path.stat().st_size > 0
    except Exception as e:
        print(f"[thumbnail_generator] Frame extraction error: {e}")
        return False


def _create_vignette_gradient(size=(1080, 1920)):
    """Creates a dark gradient overlay for top & bottom to ensure text legibility."""
    w, h = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Top gradient (fade to transparent)
    for y in range(400):
        alpha = int(190 * (1 - y / 400))
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    # Bottom gradient (fade to transparent)
    for y in range(h - 450, h):
        factor = (y - (h - 450)) / 450
        alpha = int(210 * factor)
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    return overlay


def _get_font(size=72):
    """Finds a bold font available on the system."""
    fonts_to_try = [
        "impact.ttf", "arialbd.ttf", "trebucbd.ttf", "verdana.ttf",
        "C:\\Windows\\Fonts\\impact.ttf", "C:\\Windows\\Fonts\\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for font_name in fonts_to_try:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _formulate_text_hook(title: str, hook_line: str) -> str:
    """Extracts a short 3-5 word dramatic text hook."""
    clean = (hook_line or title or "").replace("\"", "").replace("'", "").strip()
    words = clean.split()
    if len(words) <= 5:
        return clean.upper()
    return " ".join(words[:4]).upper() + "!"


def generate(video_id: int, custom_prompt: str | None = None) -> Path:
    """
    Generates a 1080x1920 YouTube Short thumbnail for video N:
      1. Extracts a frame from output/video_N.mp4 OR uses background image.
      2. Overlays dark vignette gradients + high-contrast yellow/white text hook.
      3. Overlays circular NightLoom channel logo badge.
      4. Saves to assets/images/video_N_thumbnail.png.
    """
    out_dir = config.ASSETS_DIR / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"video_{video_id}_thumbnail.png"
    video_path = config.OUTPUT_DIR / f"video_{video_id}.mp4"
    raw_frame_path = out_dir / f"video_{video_id}_thumb_raw.png"

    # Derive title & hook_line from manifest or database
    title = f"Mystery Video {video_id}"
    hook_line = "DO NOT OPEN THIS"

    manifest_path = config.ASSETS_DIR / "visuals" / f"video_{video_id}_manifest.json"
    if manifest_path.exists():
        try:
            import json
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
                shots = manifest.get("shots", [])
                if shots:
                    hook_line = shots[0].get("segment_text", hook_line)
        except Exception:
            pass

    # 1. Acquire Base Image
    base_img = None

    # Option A: Extract frame from rendered video
    if video_path.exists():
        print(f"[thumbnail_generator] Extracting crisp frame from {video_path.name} ...")
        if _extract_frame_from_video(video_path, raw_frame_path, timestamp_sec=2.0):
            base_img = Image.open(raw_frame_path).convert("RGBA")
            raw_frame_path.unlink(missing_ok=True)

    # Option B: Fallback to any background image in assets/images/
    if base_img is None:
        bg_candidates = list(out_dir.glob(f"video_{video_id}_bg_*.png")) + list(out_dir.glob(f"video_{video_id}_bg_*.jpg"))
        if bg_candidates:
            print(f"[thumbnail_generator] Using background image: {bg_candidates[0].name}")
            base_img = Image.open(bg_candidates[0]).convert("RGBA")

    # Option C: Fallback to SDXL if GPU available
    if base_img is None:
        try:
            import torch
            if torch.cuda.is_available():
                from .sdxl_generator import generate_shot
                prompt = custom_prompt or f"cinematic dark mystery scene, {hook_line}, dramatic lighting, 8k"
                print(f"[thumbnail_generator] Generating SDXL background for thumbnail {video_id} ...")
                generate_shot(prompt, raw_frame_path, format_="short", num_inference_steps=4)
                if raw_frame_path.exists():
                    base_img = Image.open(raw_frame_path).convert("RGBA")
                    raw_frame_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[thumbnail_generator] SDXL fallback skipped: {e}")

    # Option D: Fallback to dark atmospheric canvas
    if base_img is None:
        print("[thumbnail_generator] Creating dark atmospheric canvas for thumbnail...")
        base_img = Image.new("RGBA", (1080, 1920), (15, 23, 42, 255))

    # Resize/crop to exactly 1080x1920 (fill canvas)
    bw, bh = base_img.size
    target_w, target_h = 1080, 1920
    scale = max(target_w / bw, target_h / bh)
    nw, nh = int(bw * scale), int(bh * scale)
    base_img = base_img.resize((nw, nh), resample=Image.Resampling.LANCZOS)
    # Center crop
    left = (nw - target_w) // 2
    top = (nh - target_h) // 2
    img = base_img.crop((left, top, left + target_w, top + target_h))

    # 2. Add dark vignette gradient
    vignette = _create_vignette_gradient((1080, 1920))
    img = Image.alpha_composite(img, vignette)

    draw = ImageDraw.Draw(img)

    # 3. Add High-CTR Text Hook Overlay
    text_hook = _formulate_text_hook(title, hook_line)
    font = _get_font(size=78)

    words = text_hook.split()
    lines = []
    curr_line = []
    for w in words:
        curr_line.append(w)
        if len(curr_line) >= 3:
            lines.append(" ".join(curr_line))
            curr_line = []
    if curr_line:
        lines.append(" ".join(curr_line))

    # Render lines at top-center area
    start_y = 180
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (1080 - tw) // 2

        # Draw thick black stroke / outline
        stroke_w = 6
        for dx in range(-stroke_w, stroke_w + 1):
            for dy in range(-stroke_w, stroke_w + 1):
                if dx * dx + dy * dy <= stroke_w * stroke_w:
                    draw.text((tx + dx, start_y + dy), line, font=font, fill=(0, 0, 0, 255))

        # Main text in vibrant Yellow
        draw.text((tx, start_y), line, font=font, fill=(255, 255, 0, 255))
        start_y += th + 25

    # 4. Add NightLoom Logo Badge (bottom-right corner)
    logo_candidates = [
        config.ASSETS_DIR / "templates" / "logo.png",
        config.ASSETS_DIR / "avatars" / "nightloom logo.jpg",
        config.ASSETS_DIR / "templates" / "avatar_base.png",
    ]
    badge_source = None
    for cand in logo_candidates:
        if cand.exists():
            badge_source = cand
            break

    if badge_source:
        badge_size = 240
        border_width = 6

        logo_img = Image.open(badge_source).convert("RGBA")

        # Center crop to square
        lw, lh = logo_img.size
        crop_side = min(lw, lh)
        c_left = (lw - crop_side) // 2
        c_top = (lh - crop_side) // 2
        logo_img = logo_img.crop((c_left, c_top, c_left + crop_side, c_top + crop_side))
        logo_img = logo_img.resize((badge_size, badge_size), Image.Resampling.LANCZOS)

        # Create circular mask
        mask = Image.new("L", (badge_size, badge_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, badge_size, badge_size), fill=255)

        # Composite logo with circular mask
        logo_circle = Image.new("RGBA", (badge_size, badge_size), (0, 0, 0, 0))
        logo_circle.paste(logo_img, (0, 0), mask)

        # Draw white border ring around badge
        total_size = badge_size + border_width * 2
        badge_with_border = Image.new("RGBA", (total_size, total_size), (0, 0, 0, 0))
        border_draw = ImageDraw.Draw(badge_with_border)
        border_draw.ellipse((0, 0, total_size, total_size), fill=(255, 255, 255, 230))

        # Paste logo circle inside the border
        badge_with_border.paste(logo_circle, (border_width, border_width), logo_circle)

        # Position: bottom-right
        bx = 1080 - total_size - 50
        by = 1920 - total_size - 120

        img.paste(badge_with_border, (bx, by), badge_with_border)
        print(f"[thumbnail_generator] Channel logo badge overlaid from {badge_source.name}")

    # 5. Save final thumbnail
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, quality=95)
    print(f"[thumbnail_generator] THUMBNAIL GENERATED: {out_path}")

    return out_path


if __name__ == "__main__":
    vid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    generate(video_id=vid)

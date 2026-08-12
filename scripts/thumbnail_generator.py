"""
thumbnail_generator.py — generates high-CTR 1080x1920 YouTube Short thumbnails.

Combines:
  1. SDXL-Turbo AI cinematic background artwork generated specifically for the video mystery.
  2. High-impact bold text hook overlay (Yellow & White typography with heavy dark strokes).
  3. Optional circular presenter avatar badge.

Outputs:
  - assets/images/video_N_thumbnail.png
"""

import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config
from .sdxl_generator import generate_shot


def _create_vignette_gradient(size=(1080, 1920)):
    """Creates a dark gradient overlay for top & bottom to ensure text legibility."""
    w, h = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Top gradient (fade to transparent)
    for y in range(350):
        alpha = int(180 * (1 - y / 350))
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
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for font_name in fonts_to_try:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _formulate_text_hook(title: str, hook_line: str) -> str:
    """Extracts a short 3-5 word dramatic text hook."""
    clean_hook = hook_line.replace("\"", "").replace("'", "").strip()
    words = clean_hook.split()

    if len(words) <= 5:
        return clean_hook.upper()

    # Look for keywords or take first 4 words
    return " ".join(words[:4]).upper() + "!"


def generate(video_id: int, custom_prompt: str | None = None) -> Path:
    """
    Generates a 1080x1920 YouTube Short thumbnail for video N:
      1. Generates dedicated SDXL background artwork.
      2. Overlays dark gradients + high-contrast yellow/white text hook.
      3. Overlays presenter avatar badge.
      4. Saves to assets/images/video_N_thumbnail.png.
    """
    # 1. Read manifest / video info
    manifest_path = config.ASSETS_DIR / "visuals" / f"video_{video_id}_manifest.json"
    out_path = config.ASSETS_DIR / "images" / f"video_{video_id}_thumbnail.png"
    avatar_path = config.ASSETS_DIR / "templates" / "avatar_base.png"

    # Derive SDXL prompt from title/shots if available
    title = f"Mystery Video {video_id}"
    hook_line = "DO NOT OPEN THIS ENVELOPE"

    if manifest_path.exists():
        import json
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            shots = manifest.get("shots", [])
            if shots:
                hook_line = shots[0].get("segment_text", hook_line)

    prompt = custom_prompt or (
        f"cinematic dark mystery scene, {hook_line}, "
        "dramatic lighting, 8k resolution, photorealistic, highly detailed"
    )

    print(f"[thumbnail_generator] Generating SDXL background for thumbnail {video_id} ...")
    raw_sdxl_path = config.ASSETS_DIR / "images" / f"video_{video_id}_thumb_raw.png"
    generate_shot(prompt, raw_sdxl_path, format_="short", num_inference_steps=4)

    # Load & scale SDXL image to 1080x1920
    img = Image.open(raw_sdxl_path).convert("RGBA")
    img = img.resize((1080, 1920), resample=Image.Resampling.LANCZOS)
    raw_sdxl_path.unlink(missing_ok=True)

    # 2. Add dark vignette gradient
    vignette = _create_vignette_gradient((1080, 1920))
    img = Image.alpha_composite(img, vignette)

    draw = ImageDraw.Draw(img)

    # 3. Add High-CTR Text Hook Overlay
    text_hook = _formulate_text_hook(title, hook_line)
    font = _get_font(size=78)

    # Break text hook into lines of max 3 words
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
        # Measure text box
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
    logo_path = config.ASSETS_DIR / "avatars" / "nightloom logo.jpg"
    fallback_avatar_path = config.ASSETS_DIR / "templates" / "avatar_base.png"
    badge_source = logo_path if logo_path.exists() else (fallback_avatar_path if fallback_avatar_path.exists() else None)

    if badge_source:
        badge_size = 260
        border_width = 6

        logo_img = Image.open(badge_source).convert("RGBA")

        # Crop to square from center before resizing (keeps logo from stretching)
        lw, lh = logo_img.size
        crop_side = min(lw, lh)
        left = (lw - crop_side) // 2
        top  = (lh - crop_side) // 2
        logo_img = logo_img.crop((left, top, left + crop_side, top + crop_side))
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

        # Position: bottom-right, 50px from edges
        bx = 1080 - total_size - 50
        by = 1920 - total_size - 120

        img.paste(badge_with_border, (bx, by), badge_with_border)

    # Save final thumbnail
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, quality=95)
    print(f"[thumbnail_generator] THUMBNAIL GENERATED: {out_path}")

    return out_path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate(int(sys.argv[1]))
    else:
        generate(1)

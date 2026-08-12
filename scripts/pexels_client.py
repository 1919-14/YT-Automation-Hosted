"""
pexels_client.py — fetches stock video clips and photos from Pexels
to use as background media in Style B videos.

Docs: https://www.pexels.com/api/documentation/
Rate limits: 200 req/hour, 20,000 req/month (free tier).

Usage:
    from scripts import pexels_client
    results = pexels_client.fetch_shots(shots, video_id=5, format="short")
"""

import time
import urllib.request
import urllib.parse
from pathlib import Path

from . import config


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

BASE_VIDEO_URL = "https://api.pexels.com/videos/search"
BASE_PHOTO_URL = "https://api.pexels.com/v1/search"

# How long to wait between API requests to stay well under rate limits
_REQUEST_DELAY_S = 0.4


def _headers():
    if not config.PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY is not set. Add it to your .env file — "
            "get a free key at https://www.pexels.com/api/"
        )
    return {
        "Authorization": config.PEXELS_API_KEY,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YTAutomation/1.0",
    }


def _search_videos(query, orientation="portrait", per_page=5):
    """Search Pexels for video clips. Returns list of video result dicts."""
    import json

    params = urllib.parse.urlencode({
        "query": query,
        "orientation": orientation,  # portrait | landscape | square
        "per_page": per_page,
        "size": "medium",            # medium = 1080p-ish, avoids huge downloads
    })
    url = f"{BASE_VIDEO_URL}?{params}"
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data.get("videos", [])


def _search_photos(query, orientation="portrait", per_page=5):
    """Search Pexels for photos. Returns list of photo result dicts."""
    import json

    params = urllib.parse.urlencode({
        "query": query,
        "orientation": orientation,
        "per_page": per_page,
        "size": "large",
    })
    url = f"{BASE_PHOTO_URL}?{params}"
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data.get("photos", [])


def _best_video_url(video_result, prefer_hd=True):
    """Pick the best download URL from a Pexels video result."""
    files = video_result.get("video_files", [])
    # Sort by resolution, prefer HD (~1080p) to avoid massive 4K files
    files_sorted = sorted(files, key=lambda f: f.get("height", 0), reverse=True)
    for f in files_sorted:
        h = f.get("height", 0)
        if prefer_hd and h <= 1080:
            return f.get("link")
    return files_sorted[0]["link"] if files_sorted else None


def _best_photo_url(photo_result):
    """Pick the best photo src from a Pexels photo result."""
    srcs = photo_result.get("src", {})
    return srcs.get("large2x") or srcs.get("large") or srcs.get("original")


def _download(url, dest_path):
    """Download a file with a simple progress indicator."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YTAutomation/1.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(1 << 16)  # 64 KB chunks
            if not chunk:
                break
            f.write(chunk)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_shot(query, out_path, orientation="portrait", prefer_video=True):
    """
    Fetch one stock asset for a single shot.

    query:        str — the pexels_query from the visual plan
    out_path:     Path — destination (extension determines type hint)
    orientation:  "portrait" | "landscape"
    prefer_video: if True, tries video first; falls back to photo

    Returns (asset_path, asset_type) or (None, None) on failure.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if prefer_video:
        videos = _search_videos(query, orientation=orientation, per_page=3)
        time.sleep(_REQUEST_DELAY_S)
        if videos:
            url = _best_video_url(videos[0])
            if url:
                video_path = out_path.with_suffix(".mp4")
                print(f"[pexels] Downloading video -> {video_path.name}")
                _download(url, video_path)
                return video_path, "video"

    # Fallback to photo
    photos = _search_photos(query, orientation=orientation, per_page=3)
    time.sleep(_REQUEST_DELAY_S)
    if photos:
        url = _best_photo_url(photos[0])
        if url:
            photo_path = out_path.with_suffix(".jpg")
            print(f"[pexels] Downloading photo -> {photo_path.name}")
            _download(url, photo_path)
            return photo_path, "image"

    print(f"[pexels] No results for '{query}' — skipping shot.")
    return None, None


def fetch_shots(shots, video_id, format_="short", prefer_video=True):
    """
    Fetch background assets for a list of shots from the visual plan.

    shots:       list of shot dicts from visuals_planner.build_visual_plan()
    video_id:    int
    format_:     "short" | "long"
    prefer_video: try video clips before photos

    Returns a list of {shot_id, asset_path, asset_type} dicts.
    """
    orientation = "portrait" if format_ == "short" else "landscape"
    out_dir_v = config.ASSETS_DIR / "video"
    out_dir_i = config.ASSETS_DIR / "images"
    out_dir_v.mkdir(parents=True, exist_ok=True)
    out_dir_i.mkdir(parents=True, exist_ok=True)

    results = []
    for shot in shots:
        stem = f"video_{video_id}_bg_{shot['shot_id']}"
        # Use video dir as the base; fetch_shot will fix the extension
        out_path = out_dir_v / stem
        print(f"[pexels] Shot {shot['shot_id']}: querying '{shot['pexels_query']}'")
        asset_path, asset_type = fetch_shot(
            shot["pexels_query"],
            out_path,
            orientation=orientation,
            prefer_video=prefer_video,
        )
        results.append({
            "shot_id": shot["shot_id"],
            "asset_path": str(asset_path) if asset_path else None,
            "asset_type": asset_type,
        })
    return results


if __name__ == "__main__":
    # Quick test: fetch one video clip
    test_q = "dark archive office mysterious"
    out = config.ASSETS_DIR / "video" / "pexels_test"
    print(f"[pexels] Test query: '{test_q}'")
    path, kind = fetch_shot(test_q, out, orientation="portrait")
    print(f"[pexels] Result: {kind} -> {path}")

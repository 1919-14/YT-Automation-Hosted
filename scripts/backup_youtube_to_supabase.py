"""
backup_youtube_to_supabase.py — Recovery & Migration Tool.

Extracts your channel's complete upload history directly from YouTube Data API,
merges it with local SQLite series lore, and upserts all 26+ video records into
your Supabase cloud database.

Usage:
  python -m scripts.backup_youtube_to_supabase --preview
  python -m scripts.backup_youtube_to_supabase --execute
"""

import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

from . import config, youtube_uploader

# Ensure UTF-8 output encoding for terminal logging safety
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _supabase_upsert(table: str, data: list[dict]) -> bool:
    """Upserts a list of dictionaries into Supabase REST API using standard urllib."""
    url_base = getattr(config, "SUPABASE_URL", "").rstrip("/")
    key = getattr(config, "SUPABASE_KEY", "")

    if not url_base or not key:
        print("[backup] ⚠️ SUPABASE_URL or SUPABASE_KEY not configured!")
        return False

    url = f"{url_base}/rest/v1/{table}"
    headers = {
        "Content-Type": "application/json",
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Prefer": "resolution=merge-duplicates",
    }

    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 201, 204):
                return True
    except Exception as e:
        print(f"[backup] ❌ Supabase upsert error ({table}): {e}")
    return False


def fetch_all_youtube_uploads() -> list[dict]:
    """Queries YouTube Data API and returns all channel upload snippets."""
    print("[backup] 🔍 Connecting to YouTube Data API to fetch channel uploads...")
    service = youtube_uploader.get_authenticated_service()

    # Get uploads playlist ID
    res = service.channels().list(mine=True, part="contentDetails").execute()
    uploads_playlist_id = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    items = []
    next_page_token = None

    while True:
        playlist_req = service.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="snippet",
            maxResults=50,
            pageToken=next_page_token,
        )
        playlist_resp = playlist_req.execute()

        for item in playlist_resp.get("items", []):
            snippet = item["snippet"]
            items.append({
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "youtube_video_id": snippet.get("resourceId", {}).get("videoId", ""),
                "published_at": snippet.get("publishedAt", ""),
            })

        next_page_token = playlist_resp.get("nextPageToken")
        if not next_page_token:
            break

    print(f"[backup] ✅ Retrieved {len(items)} videos directly from YouTube API!")
    return items


def merge_and_build_records() -> tuple[list[dict], list[dict]]:
    """
    Merges local SQLite history with YouTube API channel uploads to construct
    the complete list of 26+ video records and active series records.
    """
    yt_uploads = fetch_all_youtube_uploads()

    # Connect to local SQLite DB
    db_path = config.PROJECT_ROOT / "data" / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Read local series
    cursor.execute("SELECT * FROM series")
    series_rows = [dict(r) for r in cursor.fetchall()]

    # Read local videos indexed by youtube_video_id or title substring
    cursor.execute("SELECT * FROM videos")
    local_videos = [dict(r) for r in cursor.fetchall()]
    local_yt_map = {v["youtube_video_id"]: v for v in local_videos if v.get("youtube_video_id")}
    local_title_map = {v["title"].lower().strip(): v for v in local_videos if v.get("title")}

    conn.close()

    # Build comprehensive video records
    combined_videos = []

    # Process in chronological order (oldest first)
    yt_uploads_sorted = sorted(yt_uploads, key=lambda x: x["published_at"])

    for idx, yt_item in enumerate(yt_uploads_sorted, start=1):
        yt_id = yt_item["youtube_video_id"]
        yt_title = yt_item["title"]
        pub_at = yt_item["published_at"]

        # Check if local record exists
        matched_local = local_yt_map.get(yt_id)
        if not matched_local:
            # Fuzzy match by title
            for t_key, l_vid in local_title_map.items():
                if t_key in yt_title.lower() or yt_title.lower() in t_key:
                    matched_local = l_vid
                    break

        if matched_local:
            # Use original local record metadata and assign youtube_video_id
            v_record = dict(matched_local)
            v_record["youtube_video_id"] = yt_id
            v_record["status"] = "uploaded"
            v_record["uploaded_at"] = pub_at
        else:
            # New video created live on HF Space
            is_long = "long" in yt_title.lower() or "part" in yt_title.lower() and "short" not in yt_title.lower()
            fmt = "long_continuous" if is_long else "short"
            cat = "horror" if "horror" in yt_title.lower() or "dark" in yt_title.lower() or "mine" in yt_title.lower() else "mystery"

            # Check if part of lighthouse series
            series_id = 1 if "light" in yt_title.lower() or "keeper" in yt_title.lower() or "brass key" in yt_title.lower() else None

            v_record = {
                "video_id": idx,
                "series_id": series_id,
                "series_part": 2 if "part 2" in yt_title.lower() else (1 if series_id else None),
                "category": cat,
                "format": fmt,
                "style": "pexels",
                "title": yt_title,
                "hook_line": yt_title,
                "ending_line": "",
                "cta": "Subscribe for Part 2 & drop your theory in the comments!",
                "script_json": json.dumps({"title": yt_title}),
                "script_hash": f"yt-{yt_id}",
                "audio_path": f"assets/audio/video_{idx}.mp3",
                "visual_manifest_path": f"assets/visuals/video_{idx}_manifest.json",
                "video_path": f"output/video_{idx}.mp4",
                "thumbnail_path": f"assets/images/video_{idx}_thumbnail.png",
                "youtube_video_id": yt_id,
                "status": "uploaded",
                "error_message": None,
                "created_at": pub_at.replace("T", " ").replace("Z", ""),
                "uploaded_at": pub_at,
            }

        v_record["video_id"] = idx
        combined_videos.append(v_record)

    return series_rows, combined_videos


def run_backup(execute: bool = False):
    series_list, video_list = merge_and_build_records()

    print(f"\n=======================================================")
    print(f"  SUPABASE BACKUP PREVIEW ({len(video_list)} TOTAL VIDEOS)")
    print(f"=======================================================")

    for v in video_list[-12:]:
        print(f"Vid #{v['video_id']:<2} | YT ID: {v['youtube_video_id']} | Status: {v['status']} | {v['title']}")

    print(f"\nSeries Records to Sync: {len(series_list)}")
    print(f"Video Records to Sync : {len(video_list)}")

    if not execute:
        print("\n💡 Run with --execute to push all records to Supabase cloud database!")
        return

    print("\n🚀 Pushing records to Supabase Cloud REST API...")
    s_ok = _supabase_upsert("series", series_list)
    v_ok = _supabase_upsert("videos", video_list)

    if s_ok and v_ok:
        print(f"\n🎉 BACKUP SUCCESSFUL! All {len(video_list)} videos and {len(series_list)} series are safely in Supabase!")
    else:
        print("\n❌ Backup failed during Supabase API push.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube to Supabase Backup Tool")
    parser.add_argument("--execute", action="store_true", help="Push records to Supabase")
    args = parser.parse_args()
    run_backup(execute=args.execute)

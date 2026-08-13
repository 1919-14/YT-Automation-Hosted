"""
youtube_uploader.py — handles YouTube Data API v3 OAuth2 authentication,
resumable video uploading, and custom thumbnail uploading.

Credentials:
  - data/client_secret.json — Google Cloud OAuth 2.0 client secret
  - data/token.json         — Cached user OAuth token (auto-created on first auth)

Usage:
  from scripts import youtube_uploader
  video_id_yt = youtube_uploader.upload_video(video_file, thumbnail_file, metadata)
"""

import os
import sys
import time
from pathlib import Path

from google import auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from . import config

# Scopes required for uploading videos and setting thumbnails
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

CLIENT_SECRET_FILE = config.PROJECT_ROOT / "data" / "client_secret.json"
TOKEN_FILE         = config.PROJECT_ROOT / "data" / "token.json"


def ensure_oauth_files():
    """Restores OAuth client secret and token files from environment secrets if missing on disk."""
    data_dir = config.PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    token_json_env = os.getenv("YOUTUBE_TOKEN_JSON")
    if token_json_env and not TOKEN_FILE.exists():
        print("[youtube_uploader] Restoring data/token.json from environment secret ...")
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(token_json_env)

    client_secret_env = os.getenv("YOUTUBE_CLIENT_SECRET_JSON")
    if client_secret_env and not CLIENT_SECRET_FILE.exists():
        print("[youtube_uploader] Restoring data/client_secret.json from environment secret ...")
        with open(CLIENT_SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(client_secret_env)


def get_authenticated_service():
    """Authenticates the user via OAuth2 and returns an active YouTube API service."""
    ensure_oauth_files()
    creds = None

    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            print(f"[youtube_uploader] Token file invalid ({e}). Requesting fresh login.")
            TOKEN_FILE.unlink(missing_ok=True)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("[youtube_uploader] Refreshing expired OAuth token ...")
                creds.refresh(Request())
            except Exception:
                print("[youtube_uploader] Token refresh failed. Re-authenticating...")
                creds = None

        if not creds:
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials not found at: {CLIENT_SECRET_FILE}\n"
                    f"Please download your client_secret.json from Google Cloud Console "
                    f"and place it at {CLIENT_SECRET_FILE}."
                )

            print(f"[youtube_uploader] Opening browser for YouTube OAuth login ...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for future runs
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        print(f"[youtube_uploader] Token cached at {TOKEN_FILE.name}")

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_file_path: Path | str,
    thumbnail_path: Path | str | None,
    metadata: dict,
    privacy_status: str = "private",
) -> str:
    """
    Uploads a video to YouTube with metadata and sets custom thumbnail.

    privacy_status: 'private', 'unlisted', or 'public'
    Returns the uploaded YouTube Video ID string.
    """
    video_file = Path(video_file_path)
    if not video_file.exists():
        raise FileNotFoundError(f"Video file to upload not found: {video_file}")

    service = get_authenticated_service()

    body = {
        "snippet": {
            "title":       metadata.get("title", "YouTube Short")[:100],
            "description": metadata.get("description", ""),
            "tags":        metadata.get("tags", []),
            "categoryId":  metadata.get("category_id", "24"),
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"[youtube_uploader] Uploading video to YouTube ({video_file.name}) ...")
    print(f"  Title      : {body['snippet']['title']}")
    print(f"  Privacy    : {privacy_status}")

    media = MediaFileUpload(
        str(video_file),
        chunksize=1024 * 1024 * 5,  # 5MB chunks
        resumable=True,
        mimetype="video/mp4",
    )

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    from tqdm import tqdm
    response = None
    with tqdm(total=100, desc="[youtube_uploader] Uploading video", unit="%") as pbar:
        last_progress = 0
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                pbar.update(progress - last_progress)
                last_progress = progress

    yt_video_id = response.get("id")
    print(f"[youtube_uploader] VIDEO UPLOAD SUCCESSFUL! YouTube Video ID: {yt_video_id}")
    print(f"[youtube_uploader] Watch URL: https://youtu.be/{yt_video_id}")

    # Set Custom Thumbnail if provided
    if thumbnail_path:
        thumb_file = Path(thumbnail_path)
        if thumb_file.exists():
            print(f"[youtube_uploader] Uploading custom thumbnail ({thumb_file.name}) ...")
            upload_thumb_path = thumb_file

            # YouTube API requires thumbnail file size < 2MB (2,097,152 bytes)
            if thumb_file.stat().st_size > 2000000:
                try:
                    from PIL import Image
                    img = Image.open(thumb_file)
                    compressed_path = thumb_file.parent / f"{thumb_file.stem}_compressed.jpg"
                    img.convert("RGB").save(compressed_path, "JPEG", quality=85, optimize=True)
                    print(f"[youtube_uploader] Compressed thumbnail from {thumb_file.stat().st_size / 1024 / 1024:.2f}MB to {compressed_path.stat().st_size / 1024 / 1024:.2f}MB")
                    upload_thumb_path = compressed_path
                except Exception as ce:
                    print(f"[youtube_uploader] Thumbnail compression warning: {ce}")

            mtype = "image/jpeg" if upload_thumb_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            for attempt in range(1, 4):
                try:
                    service.thumbnails().set(
                        videoId=yt_video_id,
                        media_body=MediaFileUpload(str(upload_thumb_path), mimetype=mtype),
                    ).execute()
                    print("[youtube_uploader] Thumbnail uploaded successfully.")
                    break
                except Exception as e:
                    print(f"[youtube_uploader] Warning: Thumbnail upload attempt {attempt}/3 failed: {e}")
                    if attempt < 3:
                        time.sleep(3)
        else:
            print(f"[youtube_uploader] Thumbnail file not found: {thumb_file}")


    return yt_video_id


if __name__ == "__main__":
    print(f"Client Secret File Path : {CLIENT_SECRET_FILE}")
    print(f"Client Secret Exists    : {CLIENT_SECRET_FILE.exists()}")

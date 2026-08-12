"""
telegram_notifier.py — safe, zero-dependency push notification & live progress stream helper.

Uses standard urllib HTTP calls to hit the Telegram Bot API.
Features live in-place message card updates (editMessageText) so progress percentages
and real-time terminal log snippets stream cleanly to your phone screen.
Does NOT throw exceptions if Telegram token is not set or network is offline.
"""

import json
import re
import time
import urllib.request
import urllib.parse
from . import config

# Store active live message IDs and edit timestamps per video_id
_LIVE_MESSAGE_IDS = {}
_LAST_EDIT_TIMES = {}
_RECENT_LOG_LINES = {}

_THROTTLE_DELAY_S = 3.0  # Minimum delay between message edits to satisfy Telegram API rate limits


def _send_api_request(method: str, payload: dict) -> dict | None:
    """Send an HTTP request to Telegram Bot API. Returns parsed JSON response dict."""
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return None

    base_url = getattr(config, "TELEGRAM_API_BASE_URL", "https://api.telegram.org/bot").rstrip("/")

    url = f"{base_url}{token}/{method}" if base_url.endswith("bot") else f"{base_url}/bot{token}/{method}"
    payload["chat_id"] = chat_id

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def notify(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a standard text message to Telegram chat."""
    res = _send_api_request("sendMessage", {
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    })
    return res is not None and res.get("ok", False)


def create_live_progress_card(video_id: int, title: str = None):
    """Creates a new live message card for a video run and stores its message_id."""
    header = f"🌌 *Night Loom Pipeline Engine* — Video `{video_id}`\n"
    if title:
        header += f"🎬 _{title}_\n"
    header += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    header += "📊 *Overall Progress:* [░░░░░░░░░░] 0%\n"
    header += "⚙️ *Current Stage:* Starting Pipeline...\n"
    header += "⏱️ *Status:* Initializing stages..."

    res = _send_api_request("sendMessage", {
        "text": header,
        "parse_mode": "Markdown",
    })
    if res and res.get("ok"):
        msg_id = res["result"]["message_id"]
        _LIVE_MESSAGE_IDS[video_id] = msg_id
        _LAST_EDIT_TIMES[video_id] = time.time()
        _RECENT_LOG_LINES[video_id] = []
        return msg_id
    return None


def update_live_progress(video_id: int, stage_num: str, stage_name: str, percent: int, log_line: str = None, force: bool = False):
    """Updates the live Telegram message card in-place with percentage bar and terminal log stream."""
    msg_id = _LIVE_MESSAGE_IDS.get(video_id)
    if not msg_id:
        # Create message card if not already created
        msg_id = create_live_progress_card(video_id)
        if not msg_id:
            return

    now = time.time()
    last_edit = _LAST_EDIT_TIMES.get(video_id, 0)
    if not force and (now - last_edit) < _THROTTLE_DELAY_S:
        return  # Throttle to stay within Telegram API rate limits

    # Track recent log lines
    if log_line:
        clean_line = re.sub(r"\x1b\[[0-9;]*m", "", log_line).strip()  # Strip ANSI color codes
        if clean_line:
            buf = _RECENT_LOG_LINES.get(video_id, [])
            buf.append(clean_line)
            if len(buf) > 4:
                buf = buf[-4:]
            _RECENT_LOG_LINES[video_id] = buf

    # Build ASCII progress bar
    bars = int(percent / 10)
    bar_str = "█" * bars + "░" * (10 - bars)

    card_text = (
        f"🌌 *Night Loom Pipeline Engine* — Video `{video_id}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Overall Progress:* [{bar_str}] {percent}%\n"
        f"⚙️ *Current Stage:* Stage {stage_num}/7 ({stage_name})\n"
    )

    recent_logs = _RECENT_LOG_LINES.get(video_id, [])
    if recent_logs:
        card_text += "\n📺 *Live Terminal Log Stream:*\n```text\n"
        card_text += "\n".join(recent_logs[-3:]) + "\n```"

    _send_api_request("editMessageText", {
        "message_id": msg_id,
        "text": card_text,
        "parse_mode": "Markdown",
    })
    _LAST_EDIT_TIMES[video_id] = now


def send_stage_start(stage_num: str, stage_name: str, video_id: int):
    """Notify stage start & update live card."""
    approx_percent = int((int(stage_num) - 1) / 7.0 * 100)
    update_live_progress(video_id, stage_num, stage_name, approx_percent, log_line=f"Starting stage {stage_num}: {stage_name}", force=True)


def send_stage_complete(stage_num: str, stage_name: str, video_id: int):
    """Notify stage completion & update live card."""
    approx_percent = int(int(stage_num) / 7.0 * 100)
    update_live_progress(video_id, stage_num, stage_name, approx_percent, log_line=f"Completed stage {stage_num}: {stage_name}", force=True)


def send_completion_card(video_id: int, title: str, youtube_url: str = None):
    """Update live card to 100% and post final video summary with YouTube link."""
    # Final update on live card
    update_live_progress(video_id, "7", "Completed & Uploaded", 100, log_line="Pipeline completed successfully!", force=True)

    msg = (
        f"🎉 *PIPELINE COMPLETE FOR VIDEO {video_id}!*\n\n"
        f"🎬 *Title:* _{title}_\n"
    )
    if youtube_url:
        msg += f"🔗 *Watch URL:* {youtube_url}\n"
    msg += "\n🧹 _Intermediate assets cleaned up._"
    notify(msg)

    # Clean up tracking dicts
    _LIVE_MESSAGE_IDS.pop(video_id, None)
    _LAST_EDIT_TIMES.pop(video_id, None)
    _RECENT_LOG_LINES.pop(video_id, None)


def send_error_alert(stage_num: str, stage_name: str, video_id: int, error_msg: str):
    """Notify when a stage fails."""
    text = (
        f"🚨 *[ALERT] STAGE {stage_num} FAILED!*\n"
        f"📹 *Video ID:* `{video_id}`\n"
        f"⚙️ *Stage:* {stage_name}\n"
        f"❌ *Error:* `{error_msg}`\n\n"
        f"💡 _Send `/retry {video_id}` to your bot to resume from this stage._"
    )
    notify(text)

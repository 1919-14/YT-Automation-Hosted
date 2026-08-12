"""
app.py — Zero-outbound Telegram Webhook Bot for Hugging Face Docker Spaces.

Architecture:
  - Telegram POSTs updates to https://vssksn-intellicredit-openenv.hf.space/webhook (inbound ✅)
  - We reply by embedding the Bot API method IN the HTTP response body (no outbound needed ✅)
  - Pipeline runs in a background thread; progress notifications use urllib through CF proxy

HF Spaces blocks ALL outbound connections. This solution requires ZERO outbound calls
to receive and respond to Telegram commands.
"""

import asyncio
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import urllib.request

# ── Force IPv4 ──────────────────────────────────────────────────────────────
_old_getaddrinfo = socket.getaddrinfo
def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _old_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _ipv4_only

# ── Bootstrap templates ──────────────────────────────────────────────────────
def ensure_baseline_templates():
    template_dir = Path("assets/templates")
    template_dir.mkdir(parents=True, exist_ok=True)
    avatar_base = template_dir / "avatar_base.png"
    if not avatar_base.exists():
        raw_url = "https://raw.githubusercontent.com/1919-14/YT-Automation-Hosted/main/assets/templates/avatar_base.png"
        try:
            print(f"[HF-Space] Downloading baseline template from {raw_url} ...")
            urllib.request.urlretrieve(raw_url, avatar_base)
            print("[HF-Space] Baseline template downloaded successfully!")
        except Exception as e:
            print(f"[HF-Space] Warning downloading template: {e}")

ensure_baseline_templates()

# ── Load config ──────────────────────────────────────────────────────────────
BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID    = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
CF_PROXY   = os.environ.get("TELEGRAM_API_BASE_URL", "").rstrip("/")
# If no proxy configured, fall back to direct (will fail on HF, but at least
# won't crash at import time)
TG_API     = CF_PROXY if CF_PROXY else "https://api.telegram.org/bot"
if not TG_API.endswith("bot"):
    TG_API = TG_API.rstrip("/") + "/bot"

print(f"[HF-Space] Telegram API endpoint: {TG_API}", flush=True)
print(f"[HF-Space] Authorized chat ID: {CHAT_ID or 'ANY'}", flush=True)

# ── Inline keyboard layout ───────────────────────────────────────────────────
MAIN_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🎬 Short (SDXL)",      "callback_data": "run_short_sdxl"},
            {"text": "📽️ Short (Pexels)",    "callback_data": "run_short_pexels"},
        ],
        [
            {"text": "📜 Long (SDXL)",        "callback_data": "run_long_sdxl"},
            {"text": "🎞️ Long (Pexels)",     "callback_data": "run_long_pexels"},
        ],
        [
            {"text": "📊 Recent Status",       "callback_data": "status_recent"},
            {"text": "🔁 Retry by ID",         "callback_data": "prompt_retry"},
        ],
    ]
}

WELCOME_TEXT = (
    "🌌 *Night Loom Control Center*\n\n"
    "Choose an operation to trigger automated video generation "
    "or manage YouTube uploads."
)

# ── Background pipeline runner ───────────────────────────────────────────────
def _run_pipeline(is_short: bool, style: str | None, video_id=None):
    try:
        from scripts import orchestrator
        orchestrator.run_pipeline(
            video_id=video_id,
            is_short=is_short,
            upload=True,
            privacy="public",
            style=style,
        )
    except Exception as e:
        print(f"[pipeline] Error: {e}", flush=True)

def _send_proactive_message(text: str):
    """Send a message proactively (requires outbound — uses urllib through CF proxy)."""
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"{TG_API}{BOT_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[notify] Could not send proactive message: {e}", flush=True)

# ── Webhook reply helpers ────────────────────────────────────────────────────
def _reply_message(chat_id, text, keyboard=None):
    """Build a sendMessage response body (embedded in HTTP response — no outbound!)."""
    r = {"method": "sendMessage", "chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        r["reply_markup"] = keyboard
    return r

def _reply_edit(chat_id, message_id, text, keyboard=None):
    """Build an editMessageText response body."""
    r = {"method": "editMessageText", "chat_id": chat_id, "message_id": message_id,
         "text": text, "parse_mode": "Markdown"}
    if keyboard:
        r["reply_markup"] = keyboard
    return r

def _answer_callback(callback_id):
    return {"method": "answerCallbackQuery", "callback_query_id": callback_id}

# ── Authorization ────────────────────────────────────────────────────────────
def _is_authorized(user_id: int) -> bool:
    if not CHAT_ID:
        return True
    return str(user_id) == CHAT_ID

# ── Update dispatcher ────────────────────────────────────────────────────────
def _handle_update(update: dict) -> dict | None:
    """Process one Telegram update dict. Returns the response body dict or None."""

    # ── Callback query (button tap) ──────────────────────────────────────────
    if "callback_query" in update:
        cq = update["callback_query"]
        user_id = cq["from"]["id"]
        cq_id   = cq["id"]
        chat_id = cq["message"]["chat"]["id"]
        msg_id  = cq["message"]["message_id"]
        data    = cq.get("data", "")

        print(f"[bot] Callback '{data}' from user_id={user_id}", flush=True)

        if not _is_authorized(user_id):
            return {"method": "answerCallbackQuery", "callback_query_id": cq_id,
                    "text": f"⛔ Unauthorized. Your ID: {user_id}"}

        if data == "run_short_sdxl":
            threading.Thread(target=_run_pipeline, kwargs={"is_short": True, "style": "sdxl"}, daemon=True).start()
            return _reply_edit(chat_id, msg_id, "🎬 *Starting Short (SDXL)...*\nPipeline is running in background!")

        if data == "run_short_pexels":
            threading.Thread(target=_run_pipeline, kwargs={"is_short": True, "style": "pexels"}, daemon=True).start()
            return _reply_edit(chat_id, msg_id, "📽️ *Starting Short (Pexels)...*\nFetching stock clips!")

        if data == "run_long_sdxl":
            threading.Thread(target=_run_pipeline, kwargs={"is_short": False, "style": "sdxl"}, daemon=True).start()
            return _reply_edit(chat_id, msg_id, "📜 *Starting Long Video (SDXL)...*\nGenerating 6+ min script!")

        if data == "run_long_pexels":
            threading.Thread(target=_run_pipeline, kwargs={"is_short": False, "style": "pexels"}, daemon=True).start()
            return _reply_edit(chat_id, msg_id, "🎞️ *Starting Long Video (Pexels)...*\nGenerating 6+ min script!")

        if data == "status_recent":
            try:
                from scripts import memory as mem
                mem.init_db()
                with mem.get_conn() as conn:
                    rows = conn.execute(
                        "SELECT video_id, title, status, format FROM videos ORDER BY video_id DESC LIMIT 5"
                    ).fetchall()
                lines = ["📊 *Recent Videos:*\n"]
                for r in rows:
                    icon = "✅" if r["status"] in ("uploaded", "rendered") else "❌" if r["status"] == "failed" else "⚙️"
                    lines.append(f"{icon} *ID {r['video_id']}* ({r['format'] or 'short'}): _{r['title'] or 'untitled'}_\n   └ `{r['status']}`")
                return _reply_edit(chat_id, msg_id, "\n".join(lines), MAIN_KEYBOARD)
            except Exception as e:
                return _reply_edit(chat_id, msg_id, f"❌ Could not fetch status: {e}", MAIN_KEYBOARD)

        if data == "prompt_retry":
            return _reply_edit(chat_id, msg_id,
                "🔁 *Retry by ID*\n\nSend: `/retry <video_id> [sdxl|pexels]`\nExample: `/retry 16 pexels`",
                MAIN_KEYBOARD)

        return _answer_callback(cq_id)

    # ── Regular message ──────────────────────────────────────────────────────
    if "message" in update:
        msg     = update["message"]
        user_id = msg["from"]["id"]
        chat_id = msg["chat"]["id"]
        text    = msg.get("text", "")

        print(f"[bot] Message '{text}' from user_id={user_id}", flush=True)

        if not _is_authorized(user_id):
            return _reply_message(chat_id,
                f"⛔ Unauthorized. Your Telegram User ID is `{user_id}`.\n"
                f"Set `TELEGRAM_CHAT_ID={user_id}` in HF Space Secrets.")

        # Commands
        cmd = text.split()[0].lower().split("@")[0] if text.startswith("/") else ""

        if cmd in ("/start", "/menu"):
            return _reply_message(chat_id, WELCOME_TEXT, MAIN_KEYBOARD)

        if cmd == "/status":
            try:
                from scripts import memory as mem
                mem.init_db()
                with mem.get_conn() as conn:
                    rows = conn.execute(
                        "SELECT video_id, title, status, format FROM videos ORDER BY video_id DESC LIMIT 5"
                    ).fetchall()
                lines = ["📊 *Recent Videos:*\n"]
                for r in rows:
                    icon = "✅" if r["status"] in ("uploaded", "rendered") else "❌" if r["status"] == "failed" else "⚙️"
                    lines.append(f"{icon} *ID {r['video_id']}*: _{r['title'] or 'untitled'}_\n   └ `{r['status']}`")
                return _reply_message(chat_id, "\n".join(lines), MAIN_KEYBOARD)
            except Exception as e:
                return _reply_message(chat_id, f"❌ Could not fetch status: {e}")

        if cmd == "/retry":
            parts = text.split()
            if len(parts) < 2:
                return _reply_message(chat_id, "💡 Usage: `/retry <video_id> [sdxl|pexels]`")
            try:
                vid = int(parts[1])
                style = parts[2] if len(parts) > 2 else None
                threading.Thread(target=_run_pipeline, kwargs={"video_id": vid, "style": style, "is_short": True}, daemon=True).start()
                return _reply_message(chat_id, f"🚀 *Retrying Video {vid}* (style: `{style or 'default'}`)...", MAIN_KEYBOARD)
            except ValueError:
                return _reply_message(chat_id, "❌ Invalid video ID.")

        # Any other text → show menu
        return _reply_message(chat_id, WELCOME_TEXT, MAIN_KEYBOARD)

    return None


# ── HTTP Server ──────────────────────────────────────────────────────────────
STATUS_HTML = """<!DOCTYPE html>
<html><head>
    <title>Night Loom Engine</title><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#f8fafc;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}
        .card{background:#1e293b;border-radius:16px;padding:32px;max-width:500px;box-shadow:0 20px 25px -5px rgba(0,0,0,.5);border:1px solid #334155}
        .status{display:inline-flex;align-items:center;gap:8px;background:#064e3b;color:#34d399;padding:6px 14px;border-radius:9999px;font-weight:600;font-size:14px;margin-bottom:16px}
        .dot{width:8px;height:8px;background:#10b981;border-radius:50%;animation:pulse 2s infinite}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
        h1{margin:0 0 12px;font-size:24px;color:#38bdf8}
        p{color:#94a3b8;line-height:1.6;margin:0 0 20px}
        ul{background:#0f172a;padding:16px 20px 16px 36px;border-radius:8px;color:#cbd5e1;margin:0}
        li{margin-bottom:8px}
    </style>
</head><body><div class="card">
    <div class="status"><span class="dot"></span>Online & Operational</div>
    <h1>🌌 Night Loom Control Engine</h1>
    <p>Autonomous 24/7 video creation pipeline active in the cloud.</p>
    <ul>
        <li>📱 <b>Telegram Bot:</b> Webhook mode — listening for commands.</li>
        <li>🎬 <b>Pexels Engine:</b> Ready for video compositing.</li>
        <li>📤 <b>YouTube Uploader:</b> Auto-publishing enabled.</li>
    </ul>
</div></body></html>"""


class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(STATUS_HTML.encode())

    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        try:
            length  = int(self.headers.get("Content-Length", 0))
            body    = self.rfile.read(length)
            update  = json.loads(body)
            print(f"[webhook] Received update_id={update.get('update_id')}", flush=True)

            response = _handle_update(update)
        except Exception as e:
            print(f"[webhook] Error parsing update: {e}", flush=True)
            response = None

        if response:
            payload = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(200)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress HTTP access logs


def run_http_server():
    port = int(os.environ.get("PORT", 7860))
    print(f"[HF-Space] Starting HTTP server on port {port}...", flush=True)
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    server.serve_forever()


# ── Webhook registration (using urllib — no httpx dependency) ────────────────
def register_webhook():
    """Register our HF Space URL as the Telegram webhook.
    Uses urllib so it works even if httpx is blocked (urllib is lower-level).
    """
    space_host = os.environ.get("SPACE_HOST", "").strip() or "vssksn-intellicredit-openenv.hf.space"
    webhook_url = f"https://{space_host}/webhook"

    if not BOT_TOKEN:
        print("[webhook] No BOT_TOKEN — skipping registration.", flush=True)
        return

    url = f"{TG_API}{BOT_TOKEN}/setWebhook"
    payload = json.dumps({
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False,
    }).encode()

    for attempt in range(1, 6):
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            if result.get("ok"):
                print(f"[webhook] Registered: {webhook_url}", flush=True)
                # Try to send startup notification (best-effort)
                if CHAT_ID:
                    try:
                        notify_url = f"{TG_API}{BOT_TOKEN}/sendMessage"
                        notify_payload = json.dumps({
                            "chat_id": CHAT_ID,
                            "text": (
                                "⚡ *Night Loom Control Center Online!*\n\n"
                                f"Webhook: `{webhook_url}`\n"
                                "Send /menu to start!"
                            ),
                            "parse_mode": "Markdown",
                        }).encode()
                        urllib.request.urlopen(
                            urllib.request.Request(notify_url, data=notify_payload,
                                                   headers={"Content-Type": "application/json"}),
                            timeout=10
                        )
                        print(f"[webhook] Startup notification sent to {CHAT_ID}", flush=True)
                    except Exception as ne:
                        print(f"[webhook] Could not send startup notification: {ne}", flush=True)
                return
            else:
                print(f"[webhook] Registration attempt {attempt} failed: {result}", flush=True)
        except Exception as e:
            wait = 5 * attempt
            print(f"[webhook] Registration attempt {attempt} error ({e}). Retrying in {wait}s...", flush=True)
            time.sleep(wait)

    print("[webhook] All registration attempts failed. Bot will still receive updates if webhook was previously set.", flush=True)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    import datetime
    print(f"\n===== Application Startup at {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} =====\n", flush=True)

    # Start HTTP server in background thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # Give HTTP server a moment to bind
    time.sleep(1)

    # Register webhook in background (non-blocking, retries internally)
    print("[HF-Space] Registering Telegram webhook...", flush=True)
    webhook_thread = threading.Thread(target=register_webhook, daemon=True)
    webhook_thread.start()

    print("[HF-Space] Bot ready! Listening for webhook updates on /webhook", flush=True)

    # Keep main thread alive
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()

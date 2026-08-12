"""
app.py — Webhook-based Telegram Bot + HTTP Status Server for Hugging Face Docker Spaces.

Architecture:
- Telegram pushes updates TO us (POST /webhook) — no outbound polling needed!
- Our HTTP server on port 7860 receives updates and feeds them to the bot Application.
- Bot replies are sent via short-lived POST calls to api.telegram.org (not blocked).
"""

import asyncio
import json
import os
import socket
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Force IPv4 DNS — same as telegram_bot.py, needed for any api.telegram.org
# call made from this process (e.g. when sending notifications).
# ──────────────────────────────────────────────────────────────────────────────
_old_getaddrinfo = socket.getaddrinfo

def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _old_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _ipv4_only

# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap templates
# ──────────────────────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────────────────────
# Global telegram Application reference (set once async setup completes)
# ──────────────────────────────────────────────────────────────────────────────
_telegram_app = None
_bot_loop: asyncio.AbstractEventLoop | None = None


# ──────────────────────────────────────────────────────────────────────────────
# HTTP Server — handles both status page (GET) and webhook (POST /webhook)
# ──────────────────────────────────────────────────────────────────────────────
STATUS_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Night Loom Engine — YT Automation Hosted</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .card { background: #1e293b; border-radius: 16px; padding: 32px; max-width: 500px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); border: 1px solid #334155; }
        .status { display: inline-flex; align-items: center; gap: 8px; background: #064e3b; color: #34d399; padding: 6px 14px; border-radius: 9999px; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
        .dot { width: 8px; height: 8px; background: #10b981; border-radius: 50%; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        h1 { margin: 0 0 12px 0; font-size: 24px; color: #38bdf8; }
        p { color: #94a3b8; line-height: 1.6; margin: 0 0 20px 0; }
        ul { background: #0f172a; padding: 16px 20px 16px 36px; border-radius: 8px; color: #cbd5e1; margin: 0; }
        li { margin-bottom: 8px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="status"><span class="dot"></span> Online & Operational</div>
        <h1>🌌 Night Loom Control Engine</h1>
        <p>Your autonomous 24/7 video creation pipeline is active in the cloud.</p>
        <ul>
            <li>📱 <b>Telegram Bot:</b> Webhook mode — connected & listening.</li>
            <li>🎬 <b>Pexels Engine:</b> Ready for instant video compositing.</li>
            <li>📤 <b>YouTube Uploader:</b> Auto-publishing enabled.</li>
        </ul>
    </div>
</body>
</html>"""


class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(STATUS_HTML.encode("utf-8"))

    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)

        # Acknowledge immediately — Telegram expects a fast 200 OK
        self.send_response(200)
        self.end_headers()

        # Feed update to the telegram Application running in the bot thread
        if _telegram_app is not None and _bot_loop is not None:
            try:
                from telegram import Update
                update = Update.de_json(json.loads(body), _telegram_app.bot)
                asyncio.run_coroutine_threadsafe(
                    _telegram_app.process_update(update),
                    _bot_loop,
                )
            except Exception as e:
                print(f"[webhook] Error processing update: {e}", flush=True)
        else:
            print("[webhook] Received update but bot not ready yet — ignored.", flush=True)

    def log_message(self, format, *args):
        pass  # suppress HTTP access logs


def run_http_server():
    port = int(os.environ.get("PORT", 7860))
    print(f"[HF-Space] Starting HTTP Server on port {port}...", flush=True)
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    server.serve_forever()


# ──────────────────────────────────────────────────────────────────────────────
# Telegram Bot — webhook mode (no polling!)
# ──────────────────────────────────────────────────────────────────────────────
async def run_telegram_bot():
    global _telegram_app, _bot_loop

    from scripts.telegram_bot import build_application, register_webhook

    # Expose the bot loop so the webhook handler can submit updates
    _bot_loop = asyncio.get_running_loop()

    # Build and initialize the Application
    app = build_application()
    _telegram_app = app

    print("[telegram_bot] Initializing bot...", flush=True)
    await app.initialize()
    await app.start()
    print("[telegram_bot] Bot started! Registering webhook...", flush=True)

    # Register the webhook with Telegram
    await register_webhook(app.bot)

    print("[telegram_bot] Webhook registered. Ready to receive commands!", flush=True)

    # Block forever — updates arrive via HTTP POST from Telegram
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.stop()
        await app.shutdown()


def main():
    print(f"\n===== Application Startup at {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} =====\n", flush=True)

    # Start HTTP server in background thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # Run telegram bot in main thread (blocking)
    print("[HF-Space] Starting Telegram Bot in webhook mode...", flush=True)
    asyncio.run(run_telegram_bot())


if __name__ == "__main__":
    main()

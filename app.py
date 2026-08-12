"""
app.py — Pure Python Web Server & Telegram Bot Launcher for Hugging Face Docker Spaces.

Hosts a lightweight HTTP status page on port 7860 (Hugging Face Space requirement)
and launches telegram_bot.py in a background thread. Zero extra web framework dependencies!
"""

import http.server
import os
import socketserver
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

# Auto-download baseline templates if missing at runtime
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

# Launch Telegram bot in a dedicated background daemon thread
def run_telegram_bot():
    print("[HF-Space] Launching Telegram Control Bot in background...")
    try:
        subprocess.run([sys.executable, "-m", "scripts.telegram_bot"])
    except Exception as e:
        print(f"[HF-Space] Telegram Bot process error: {e}")

bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
bot_thread.start()

# Pure Python HTTP Server on port 7860
class StatusHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = """<!DOCTYPE html>
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
        li:last-child { margin-bottom: 0; }
    </style>
</head>
<body>
    <div class="card">
        <div class="status"><span class="dot"></span> Online & Operational</div>
        <h1>🌌 Night Loom Control Engine</h1>
        <p>Your autonomous 24/7 video creation pipeline is active in the cloud.</p>
        <ul>
            <li>📱 <b>Telegram Bot:</b> Connected & listening for 1-tap commands.</li>
            <li>🎬 <b>Pexels Engine:</b> Ready for instant video compositing.</li>
            <li>📤 <b>YouTube Uploader:</b> Auto-publishing enabled.</li>
        </ul>
    </div>
</body>
</html>"""
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        # Silence HTTP access logs to keep console output clean
        pass

def run_http_server():
    port = int(os.environ.get("PORT", 7860))
    print(f"[HF-Space] Starting HTTP Status Server on port {port}...")
    with socketserver.TCPServer(("0.0.0.0", port), StatusHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    run_http_server()

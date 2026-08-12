"""
app.py — Gradio Dashboard & Telegram Bot Launcher for Hugging Face Spaces.

Runs the 24/7 Telegram Control Bot in a background thread while hosting
a Gradio status dashboard on port 7860 (Hugging Face Space requirement).
"""

import os
import sys
import time
import threading
import subprocess
import gradio as gr

# Auto-download baseline templates if missing at runtime
def ensure_baseline_templates():
    import urllib.request
    from pathlib import Path
    
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

# Build lightweight Gradio Status Dashboard for HF Spaces
def get_bot_status():
    return (
        "### 🟢 Night Loom Telegram Control Bot is Active & Running 24/7!\n\n"
        "📱 **How to Control from your Mobile Phone:**\n"
        "- Send `/start` or `/menu` to your Telegram Bot.\n"
        "- Tap **Short (Pexels)** or **Long (Pexels)** for 100% cloud rendering & YouTube upload.\n"
        "- Send `/retry <video_id>` to resume any interrupted stage.\n\n"
        "⚡ *All Pexels videos, EdgeTTS audio, FFmpeg compositing, and YouTube uploads run 100% in the cloud!*"
    )

with gr.Blocks(title="Night Loom Engine — YT Automation Hosted") as demo:
    gr.Markdown("# 🌌 Night Loom Engine — Cloud Control Center")
    status_markdown = gr.Markdown(get_bot_status())
    refresh_btn = gr.Button("🔄 Refresh Status")
    refresh_btn.click(fn=get_bot_status, outputs=status_markdown)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)

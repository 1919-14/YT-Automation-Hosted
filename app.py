"""
app.py — Gradio Control Dashboard for Night Loom YT Automation on Hugging Face Spaces.

A full web UI to trigger pipelines, monitor video status, and stream live logs
directly from the browser. No Telegram or outbound connections required.
"""

import os
import sys
import time
import threading
import datetime
from pathlib import Path
import urllib.request

import gradio as gr

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

# ── Global log buffer ────────────────────────────────────────────────────────
_LOG_LINES: list[str] = []
_LOG_LOCK = threading.Lock()
_MAX_LOG = 200

def _log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with _LOG_LOCK:
        _LOG_LINES.append(line)
        if len(_LOG_LINES) > _MAX_LOG:
            _LOG_LINES.pop(0)

def get_log_text() -> str:
    with _LOG_LOCK:
        return "\n".join(_LOG_LINES[-80:]) if _LOG_LINES else "No logs yet. Run a pipeline to see output here."

# ── Pipeline state ────────────────────────────────────────────────────────────
_pipeline_running = False
_pipeline_lock = threading.Lock()

def _run_pipeline_bg(is_short: bool, style: str, video_id: int | None = None):
    global _pipeline_running
    with _pipeline_lock:
        if _pipeline_running:
            _log("⚠️ A pipeline is already running. Please wait.")
            return
        _pipeline_running = True

    try:
        _log(f"🚀 Starting {'Short' if is_short else 'Long'} pipeline (style={style}, video_id={video_id})...")
        from scripts import orchestrator
        orchestrator.run_pipeline(
            video_id=video_id,
            is_short=is_short,
            upload=True,
            privacy="public",
            style=style,
        )
        _log("✅ Pipeline completed successfully!")
    except Exception as e:
        _log(f"❌ Pipeline error: {e}")
    finally:
        with _pipeline_lock:
            _pipeline_running = False

# ── Status helpers ────────────────────────────────────────────────────────────
def get_status_df():
    """Returns list of rows for gr.DataFrame."""
    try:
        from scripts import memory as mem
        mem.init_db()
        with mem.get_conn() as conn:
            rows = conn.execute(
                """SELECT video_id, title, status, format, created_at
                   FROM videos ORDER BY video_id DESC LIMIT 20"""
            ).fetchall()
        if not rows:
            return [["—", "No videos yet", "—", "—", "—"]]
        return [
            [
                r["video_id"],
                (r["title"] or "untitled")[:60],
                r["status"],
                r["format"] or "short",
                (r["created_at"] or "")[:16],
            ]
            for r in rows
        ]
    except Exception as e:
        return [["error", str(e), "—", "—", "—"]]

def get_pipeline_status_label():
    with _pipeline_lock:
        return "🔴 Running..." if _pipeline_running else "🟢 Idle — Ready to launch"

# ── Button actions ─────────────────────────────────────────────────────────────
def trigger_pipeline(is_short: bool, style: str):
    if _pipeline_running:
        return "⚠️ A pipeline is already running! Please wait for it to finish."
    t = threading.Thread(target=_run_pipeline_bg, kwargs={"is_short": is_short, "style": style}, daemon=True)
    t.start()
    label = f"{'Short' if is_short else 'Long'} ({style.upper()})"
    return f"🚀 **{label} pipeline launched!** Check the Live Logs tab below."

def trigger_retry(video_id_str: str, style: str):
    try:
        vid = int(video_id_str.strip())
    except ValueError:
        return "❌ Invalid video ID — enter a number."
    if _pipeline_running:
        return "⚠️ A pipeline is already running!"
    t = threading.Thread(
        target=_run_pipeline_bg,
        kwargs={"is_short": True, "style": style or "pexels", "video_id": vid},
        daemon=True,
    )
    t.start()
    return f"🔁 Retrying Video ID **{vid}** (style={style or 'pexels'})..."

def refresh_status():
    return get_status_df(), get_pipeline_status_label()

def refresh_logs():
    return get_log_text()

# ── Gradio UI ─────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
/* ── Root font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

body, .gradio-container {
    font-family: 'Inter', sans-serif !important;
    background: #0f172a !important;
}

/* ── Page header card ── */
.nl-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 60%, #1a1040 100%);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 28px 32px;
    margin-bottom: 8px;
    text-align: center;
}
.nl-header h1 {
    font-size: 2rem;
    font-weight: 700;
    color: #38bdf8;
    margin: 0 0 6px 0;
    letter-spacing: -0.5px;
}
.nl-header p {
    color: #94a3b8;
    font-size: 0.95rem;
    margin: 0;
}

/* ── Status pill ── */
.status-pill {
    display: inline-block;
    background: #064e3b;
    color: #34d399;
    border-radius: 9999px;
    padding: 4px 14px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 10px;
    animation: glow 2s ease-in-out infinite alternate;
}
@keyframes glow {
    from { box-shadow: 0 0 4px #10b981; }
    to   { box-shadow: 0 0 12px #10b981; }
}

/* ── Section label ── */
.section-label {
    color: #64748b;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 6px;
    padding-left: 2px;
}

/* ── Primary buttons ── */
.btn-primary button {
    background: linear-gradient(135deg, #0ea5e9, #6366f1) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    color: white !important;
    transition: opacity 0.2s !important;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3) !important;
}
.btn-primary button:hover { opacity: 0.85 !important; }

.btn-pexels button {
    background: linear-gradient(135deg, #10b981, #0891b2) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3) !important;
}
.btn-pexels button:hover { opacity: 0.85 !important; }

.btn-long button {
    background: linear-gradient(135deg, #a855f7, #ec4899) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(168, 85, 247, 0.3) !important;
}
.btn-long button:hover { opacity: 0.85 !important; }

.btn-long-pexels button {
    background: linear-gradient(135deg, #f59e0b, #ef4444) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3) !important;
}
.btn-long-pexels button:hover { opacity: 0.85 !important; }

.btn-retry button {
    background: linear-gradient(135deg, #334155, #475569) !important;
    border: 1px solid #64748b !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    color: #e2e8f0 !important;
}

/* ── Output textbox ── */
.output-box textarea {
    background: #1e293b !important;
    color: #34d399 !important;
    border: 1px solid #334155 !important;
    border-radius: 10px !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-size: 0.82rem !important;
}

/* ── Log box ── */
.log-box textarea {
    background: #020617 !important;
    color: #a3e635 !important;
    border: 1px solid #1e293b !important;
    border-radius: 10px !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-size: 0.78rem !important;
    line-height: 1.5 !important;
}

/* ── Dataframe ── */
.custom-df table {
    background: #1e293b !important;
    color: #e2e8f0 !important;
    border-radius: 10px !important;
}
.custom-df th {
    background: #0f172a !important;
    color: #38bdf8 !important;
    font-weight: 600 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.5px !important;
}

/* ── Number input ── */
.retry-input input {
    background: #1e293b !important;
    color: #e2e8f0 !important;
    border: 1px solid #334155 !important;
    border-radius: 10px !important;
}
"""

with gr.Blocks(
    theme=gr.themes.Base(
        primary_hue=gr.themes.colors.sky,
        neutral_hue=gr.themes.colors.slate,
        font=gr.themes.GoogleFont("Inter"),
    ),
    css=CUSTOM_CSS,
    title="🌌 Night Loom Control Engine",
) as demo:

    # ── Header ──────────────────────────────────────────────────────────────
    gr.HTML("""
    <div class="nl-header">
        <h1>🌌 Night Loom Control Engine</h1>
        <p>Autonomous YouTube Automation Pipeline — 24/7 Cloud Mode</p>
        <span class="status-pill">● Online & Operational</span>
    </div>
    """)

    # ── Pipeline Launcher ───────────────────────────────────────────────────
    gr.HTML('<div class="section-label">🚀 Launch Pipeline</div>')

    with gr.Row():
        btn_short_sdxl = gr.Button(
            "🎬 Short Video\nSDXL (AI Images)",
            elem_classes="btn-primary", scale=1
        )
        btn_short_pexels = gr.Button(
            "📽️ Short Video\nPexels (Stock Clips)",
            elem_classes="btn-pexels", scale=1
        )
        btn_long_sdxl = gr.Button(
            "📜 Long Video (6+ min)\nSDXL (AI Images)",
            elem_classes="btn-long", scale=1
        )
        btn_long_pexels = gr.Button(
            "🎞️ Long Video (6+ min)\nPexels (Stock Clips)",
            elem_classes="btn-long-pexels", scale=1
        )

    launch_status = gr.Markdown(
        "👆 Tap any button above to launch a video generation pipeline.",
        elem_classes="output-box"
    )

    # ── Pipeline Status ─────────────────────────────────────────────────────
    gr.HTML('<div class="section-label" style="margin-top:20px">⚙️ Pipeline Status</div>')

    with gr.Row():
        status_label = gr.Markdown(get_pipeline_status_label())
        refresh_btn = gr.Button("🔄 Refresh", scale=0, size="sm")

    # ── Video History ───────────────────────────────────────────────────────
    gr.HTML('<div class="section-label" style="margin-top:20px">📊 Video History</div>')

    history_table = gr.DataFrame(
        value=get_status_df(),
        headers=["ID", "Title", "Status", "Format", "Created"],
        datatype=["number", "str", "str", "str", "str"],
        interactive=False,
        elem_classes="custom-df",
    )

    # ── Retry Panel ──────────────────────────────────────────────────────────
    with gr.Accordion("🔁 Retry Specific Video by ID", open=False):
        with gr.Row():
            retry_id = gr.Textbox(
                label="Video ID",
                placeholder="e.g. 16",
                scale=1,
                elem_classes="retry-input"
            )
            retry_style = gr.Dropdown(
                choices=["pexels", "sdxl"],
                value="pexels",
                label="Style",
                scale=1,
            )
            retry_btn = gr.Button("🔁 Retry", elem_classes="btn-retry", scale=0)
        retry_status = gr.Markdown("")

    # ── Live Logs ─────────────────────────────────────────────────────────
    gr.HTML('<div class="section-label" style="margin-top:20px">📡 Live Logs</div>')

    log_box = gr.Textbox(
        value=get_log_text(),
        lines=20,
        max_lines=20,
        label="",
        interactive=False,
        elem_classes="log-box",
    )

    with gr.Row():
        log_refresh_btn = gr.Button("🔄 Refresh Logs", scale=0, size="sm")
        gr.Markdown(
            "_Logs auto-refresh every 5 seconds while a pipeline is running._",
            scale=1
        )

    # ── Footer ──────────────────────────────────────────────────────────────
    gr.HTML("""
    <div style="text-align:center;color:#334155;font-size:0.75rem;margin-top:24px;padding-top:16px;border-top:1px solid #1e293b;">
        Night Loom Engine — Hugging Face Spaces Edition
    </div>
    """)

    # ── Wire up buttons ───────────────────────────────────────────────────
    btn_short_sdxl.click(
        fn=lambda: trigger_pipeline(True, "sdxl"),
        outputs=launch_status,
    )
    btn_short_pexels.click(
        fn=lambda: trigger_pipeline(True, "pexels"),
        outputs=launch_status,
    )
    btn_long_sdxl.click(
        fn=lambda: trigger_pipeline(False, "sdxl"),
        outputs=launch_status,
    )
    btn_long_pexels.click(
        fn=lambda: trigger_pipeline(False, "pexels"),
        outputs=launch_status,
    )

    retry_btn.click(
        fn=trigger_retry,
        inputs=[retry_id, retry_style],
        outputs=retry_status,
    )

    refresh_btn.click(
        fn=refresh_status,
        outputs=[history_table, status_label],
    )

    log_refresh_btn.click(
        fn=refresh_logs,
        outputs=log_box,
    )

    # Auto-refresh every 5 seconds
    demo.load(fn=refresh_logs, outputs=log_box, every=5)
    demo.load(fn=refresh_status, outputs=[history_table, status_label], every=10)


if __name__ == "__main__":
    _log("🌌 Night Loom Control Engine starting...")
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )

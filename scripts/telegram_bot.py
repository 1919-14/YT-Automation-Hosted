"""
telegram_bot.py — Telegram Remote Control Center for Night Loom YouTube Pipeline.

Allows 1-tap mobile execution of video creation pipelines, long-form videos (SDXL / Pexels),
and remote video retries directly from your phone.

Usage:
    python -m scripts.telegram_bot
"""

import asyncio
import logging
import os
import socket
import sys
import threading
from pathlib import Path

# Force IPv4 resolution for all socket connections in this process.
# Hugging Face Space Linux containers often have IPv6 enabled in DNS,
# but IPv6 egress is blocked/unreachable, causing 30s ConnectTimeout
# on api.telegram.org when asyncio attempts IPv6 first.
_old_getaddrinfo = socket.getaddrinfo

def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _old_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _ipv4_only_getaddrinfo


from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import config
from . import memory as mem
from . import orchestrator

# Enable python-telegram-bot logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("telegram_bot")


def _is_authorized(user_id: int) -> bool:
    """Security check: only allow requests from TELEGRAM_CHAT_ID."""
    allowed_chat_id = config.TELEGRAM_CHAT_ID
    if not allowed_chat_id:
        return True  # If chat ID is not set yet, allow initial setup
    return str(user_id) == str(allowed_chat_id)


def _build_main_keyboard() -> InlineKeyboardMarkup:
    """Build the 1-tap interactive menu buttons."""
    keyboard = [
        [
            InlineKeyboardButton("🎬 Short (SDXL)", callback_data="run_short_sdxl"),
            InlineKeyboardButton("📽️ Short (Pexels)", callback_data="run_short_pexels"),
        ],
        [
            InlineKeyboardButton("📜 Long Video (SDXL)", callback_data="run_long_sdxl"),
            InlineKeyboardButton("🎞️ Long Video (Pexels)", callback_data="run_long_pexels"),
        ],
        [
            InlineKeyboardButton("📊 Recent Status", callback_data="status_recent"),
            InlineKeyboardButton("🔁 Retry by ID", callback_data="prompt_retry"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _run_pipeline_background(video_id=None, is_short=True, style=None):
    """Executes pipeline in a worker thread so bot stays 100% responsive."""
    try:
        orchestrator.run_pipeline(
            video_id=video_id,
            is_short=is_short,
            upload=True,
            privacy="public",
            style=style,
        )
    except Exception as e:
        print(f"[telegram_bot] Pipeline execution failed: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and /menu commands."""
    user_id = update.effective_user.id
    print(f"[telegram_bot] Received command from user_id: {user_id} (allowed: {config.TELEGRAM_CHAT_ID})")
    
    if not _is_authorized(user_id):
        print(f"[telegram_bot] Blocked unauthorized user_id: {user_id}")
        await update.message.reply_text(f"⛔ Unauthorized access. Your User ID is `{user_id}` (allowed: `{config.TELEGRAM_CHAT_ID}`).", parse_mode="Markdown")
        return

    welcome_text = (
        "🌌 *Night Loom Control Center*\n\n"
        "Welcome! Choose an operation below to trigger automated video generation "
        "or manage YouTube uploads directly from your phone."
    )
    await update.message.reply_markdown(welcome_text, reply_markup=_build_main_keyboard())


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — shows recent videos and DB state."""
    user_id = update.effective_user.id
    print(f"[telegram_bot] /status command from user_id: {user_id}")
    if not _is_authorized(user_id):
        return

    mem.init_db()
    with mem.get_conn() as conn:
        rows = conn.execute(
            "SELECT video_id, title, status, format, created_at FROM videos ORDER BY video_id DESC LIMIT 5"
        ).fetchall()

    if not rows:
        await update.message.reply_text("📊 No videos found in database.")
        return

    lines = ["📊 *Recent Videos Status:*\n"]
    for r in rows:
        v_id = r["video_id"]
        title = r["title"] or f"video_{v_id}"
        status = r["status"]
        fmt = r["format"] or "short"
        icon = "✅" if status in ("uploaded", "rendered") else "⚙️" if status != "failed" else "❌"
        lines.append(f"{icon} *ID {v_id}* ({fmt}): _{title}_\n   └ Status: `{status}`")

    await update.message.reply_markdown("\n".join(lines), reply_markup=_build_main_keyboard())


async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /retry <video_id> [style] command."""
    user_id = update.effective_user.id
    print(f"[telegram_bot] /retry command from user_id: {user_id}")
    if not _is_authorized(user_id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("💡 Usage: `/retry <video_id> [sdxl|pexels]`\nExample: `/retry 16 pexels`", parse_mode="Markdown")
        return

    try:
        video_id = int(args[0])
        style = args[1] if len(args) > 1 else None
    except ValueError:
        await update.message.reply_text("❌ Invalid Video ID. Please provide a numeric ID.")
        return

    await update.message.reply_markdown(f"🚀 *Retrying Video {video_id}* (style: `{style or 'default'}`)...\nNotifications will be pushed per stage!")
    threading.Thread(
        target=_run_pipeline_background,
        kwargs={"video_id": video_id, "style": style},
        daemon=True,
    ).start()


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 1-tap menu button clicks."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    print(f"[telegram_bot] Button clicked '{query.data}' by user_id: {user_id}")

    if not _is_authorized(user_id):
        await query.edit_message_text(f"⛔ Unauthorized user_id: `{user_id}`.", parse_mode="Markdown")
        return

    data = query.data

    if data == "run_short_sdxl":
        await query.edit_message_text("🎬 *Starting New Short (SDXL AI Visuals)...*\nGenerating script & starting background pipeline!", parse_mode="Markdown")
        threading.Thread(target=_run_pipeline_background, kwargs={"is_short": True, "style": "sdxl"}, daemon=True).start()

    elif data == "run_short_pexels":
        await query.edit_message_text("📽️ *Starting New Short (Pexels HD Footage)...*\nGenerating script & fetching stock video clips!", parse_mode="Markdown")
        threading.Thread(target=_run_pipeline_background, kwargs={"is_short": True, "style": "pexels"}, daemon=True).start()

    elif data == "run_long_sdxl":
        await query.edit_message_text("📜 *Starting New Long Video (SDXL Widescreen)...*\nGenerating 6+ minute story script & background visuals!", parse_mode="Markdown")
        threading.Thread(target=_run_pipeline_background, kwargs={"is_short": False, "style": "sdxl"}, daemon=True).start()

    elif data == "run_long_pexels":
        await query.edit_message_text("🎞️ *Starting New Long Video (Pexels HD Footage)...*\nGenerating 6+ minute story script & stock video footage!", parse_mode="Markdown")
        threading.Thread(target=_run_pipeline_background, kwargs={"is_short": False, "style": "pexels"}, daemon=True).start()

    elif data == "status_recent":
        mem.init_db()
        with mem.get_conn() as conn:
            rows = conn.execute(
                "SELECT video_id, title, status, format FROM videos ORDER BY video_id DESC LIMIT 5"
            ).fetchall()
        lines = ["📊 *Recent Videos Status:*\n"]
        for r in rows:
            v_id = r["video_id"]
            title = r["title"] or f"video_{v_id}"
            status = r["status"]
            icon = "✅" if status in ("uploaded", "rendered") else "⚙️" if status != "failed" else "❌"
            lines.append(f"{icon} *ID {v_id}*: _{title}_\n   └ Status: `{status}`")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=_build_main_keyboard())

    elif data == "prompt_retry":
        await query.edit_message_text(
            "🔁 *Retry Video by ID*\n\nSend command: `/retry <video_id> [sdxl|pexels]`\nExample: `/retry 16 pexels`",
            parse_mode="Markdown",
            reply_markup=_build_main_keyboard(),
        )


async def generic_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler for any message to help user initialize and get their User ID."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    print(f"[telegram_bot] Generic message '{update.message.text}' from user_id: {user_id}")
    
    # If the user sends anything else, show the main menu if authorized or report their ID
    if _is_authorized(user_id):
        await update.message.reply_markdown(
            "🌌 *Night Loom Control Center*",
            reply_markup=_build_main_keyboard()
        )
    else:
        await update.message.reply_text(
            f"⛔ Unauthorized. Your Telegram User ID is `{user_id}`.\n"
            f"Set TELEGRAM_CHAT_ID={user_id} in HF Space Secrets.",
            parse_mode="Markdown"
        )


def build_application() -> Application:
    """Build and return the Application with all handlers registered.
    Called by app.py (webhook mode on HF Space) or main() (polling for local dev).
    """
    from telegram.request import HTTPXRequest

    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN is not set!", flush=True)
        sys.exit(1)

    req = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = (
        Application.builder()
        .token(token)
        .request(req)
        .get_updates_request(req)
        .build()
    )
    app.add_handler(CommandHandler(["start", "menu"], start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), generic_message_handler))

    async def error_handler(update, context):
        print(f"[telegram_bot] ERROR: {context.error}", flush=True)
        logger.error("Exception while handling an update:", exc_info=context.error)

    app.add_error_handler(error_handler)
    return app


async def register_webhook(bot):
    """Tell Telegram where to send updates (our HF Space public URL).
    Called once after app.initialize() in webhook mode.
    """
    # HF Space public URL is exposed via the SPACE_HOST env var
    space_host = os.environ.get("SPACE_HOST", "").strip()
    if not space_host:
        print("[telegram_bot] SPACE_HOST env var not set — cannot register webhook!", flush=True)
        print("[telegram_bot] Set it in HF Space Secrets as: SPACE_HOST=your-space-name.hf.space", flush=True)
        return

    webhook_url = f"https://{space_host}/webhook"
    try:
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        )
        print(f"[telegram_bot] Webhook registered: {webhook_url}", flush=True)

        # Send startup notification now that webhook is live
        chat_id = config.TELEGRAM_CHAT_ID
        if chat_id:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "⚡ *Night Loom Control Center Online!*\n\n"
                    f"Webhook active at `{webhook_url}`\n"
                    "Send /menu to start generating videos!"
                ),
                parse_mode="Markdown",
            )
            print(f"[telegram_bot] Startup notification sent to {chat_id}", flush=True)
    except Exception as e:
        print(f"[telegram_bot] Failed to register webhook: {e}", flush=True)


# ─────────────────────────────────────────────────────────
# Local development entry point (uses polling — not for HF!)
# ─────────────────────────────────────────────────────────
async def _run_local():
    """Run bot with polling — ONLY for local development on your PC."""
    app = build_application()
    await app.initialize()
    # Delete any webhook so polling works
    await app.bot.delete_webhook(drop_pending_updates=False)
    await app.start()
    await app.updater.start_polling(
        poll_interval=1.0,
        timeout=10,
        allowed_updates=Update.ALL_TYPES,
    )
    print("[telegram_bot] Local polling started! Send /menu to your bot.", flush=True)
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():
    """Entry point for LOCAL development only. HF Space uses app.py instead."""
    print("=======================================================", flush=True)
    print("NIGHT LOOM BOT — LOCAL DEV MODE (polling)", flush=True)
    print(f"   Authorized Chat ID: {config.TELEGRAM_CHAT_ID or 'ANY'}", flush=True)
    print("=======================================================", flush=True)
    asyncio.run(_run_local())


if __name__ == "__main__":
    main()

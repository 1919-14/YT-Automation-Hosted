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
import sys
import threading
from pathlib import Path

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


async def _on_startup(application: Application):
    """Notify the user on Telegram that the HF Space has started and is ready."""
    chat_id = config.TELEGRAM_CHAT_ID
    if chat_id:
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text="⚡ *Night Loom Control Center Online!*\n\nHugging Face Space is connected and ready to go. Send /menu to start!",
                parse_mode="Markdown"
            )
            print(f"[telegram_bot] Startup notification sent to chat_id: {chat_id}", flush=True)
        except Exception as e:
            print(f"[telegram_bot] Could not send startup notification: {e}", flush=True)


def _build_app(token: str):
    """Build a fresh Application instance. Must be called on every retry since
    run_polling() destroys the asyncio event loop when it exits."""
    from telegram.request import HTTPXRequest

    req = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=20.0,
    )
    app = (
        Application.builder()
        .token(token)
        .request(req)
        .get_updates_request(req)
        .post_init(_on_startup)
        .build()
    )
    app.add_handler(CommandHandler(["start", "menu"], start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), generic_message_handler))

    # Log ALL errors that happen during polling so nothing is silently swallowed
    async def error_handler(update, context):
        print(f"[telegram_bot] ERROR during update processing: {context.error}", flush=True)
        logger.error("Exception while handling an update:", exc_info=context.error)

    app.add_error_handler(error_handler)
    return app


def main():
    import time

    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN is not set in .env file.", flush=True)
        print("Create a bot via @BotFather on Telegram, copy token to .env, and re-run.", flush=True)
        sys.exit(1)

    print("=======================================================", flush=True)
    print("NIGHT LOOM TELEGRAM CONTROL BOT STARTING...", flush=True)
    print(f"   Authorized Chat ID: {config.TELEGRAM_CHAT_ID or 'ANY (Initial Setup)'}", flush=True)
    print("=======================================================", flush=True)

    attempt = 0
    while True:
        attempt += 1
        print(f"[telegram_bot] Starting bot (attempt #{attempt})...", flush=True)
        try:
            app = _build_app(token)
            print("[telegram_bot] Bot listener running! Send /menu to your bot on Telegram.", flush=True)
            # poll_interval=1.0 → poll every 1 second
            # timeout=10 → short long-poll to avoid HF proxy dropping idle connections
            app.run_polling(
                bootstrap_retries=5,
                poll_interval=1.0,
                timeout=10,
                allowed_updates=Update.ALL_TYPES,
            )
            break
        except Exception as e:
            print(f"[telegram_bot] Crashed ({type(e).__name__}: {e}). Restarting in 5 seconds...", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()

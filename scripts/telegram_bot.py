"""
telegram_bot.py — Telegram Remote Control Center for Night Loom YouTube Pipeline.

Allows 1-tap mobile execution of video creation pipelines, long-form videos (SDXL / Pexels),
and remote video retries directly from your phone.

Usage:
    python -m scripts.telegram_bot
"""

import asyncio
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
    if not _is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized access. Your User ID is not allowed.")
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

    if not _is_authorized(query.from_user.id):
        await query.edit_message_text("⛔ Unauthorized.")
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


def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("❌ Error: TELEGRAM_BOT_TOKEN is not set in .env file.")
        print("💡 Create a bot via @BotFather on Telegram, copy token to .env, and re-run.")
        sys.exit(1)

    print("=======================================================")
    print("🤖 NIGHT LOOM TELEGRAM CONTROL BOT STARTING...")
    print(f"   Authorized Chat ID: {config.TELEGRAM_CHAT_ID or 'ANY (Initial Setup)'}")
    print("=======================================================")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler(["start", "menu"], start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("retry", retry_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("[telegram_bot] Bot listener running! Send /menu to your bot on Telegram.")
    app.run_polling()


if __name__ == "__main__":
    main()

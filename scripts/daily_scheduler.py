"""
daily_scheduler.py — 24/7 Real-Time Auto-Pilot Engine for YT-Automation-Hosted.

Features:
  - 6 Fixed Global Time Windows (UTC/IST/EST overlap targeting India & US).
  - Deterministic Daily Organic Random Minute Picker (unique per slot per day).
  - Persistent 24/7 Daemon Loop: logs heartbeats & checks trigger times every 30s
    to keep HF Space active and prevent container sleep.
  - Executes live video creation using Pexels stock video mode (style="pexels").
"""

import datetime
import random
import threading
import time
from pathlib import Path

from . import config, memory, orchestrator

# ── 6 Fixed Global Windows (UTC) ──────────────────────────────────────────────
# Slot 1: Short #1 | 01:30–03:30 UTC | 07:00–09:00 IST (India Morning)
# Slot 2: Short #2 | 07:30–09:30 UTC | 13:00–15:00 IST (India Lunch)
# Slot 3: Long #1  | 11:30–13:30 UTC | 17:00–19:00 IST / 07:30–09:30 EST (Long Anchor)
# Slot 4: Short #3 | 14:00–16:00 UTC | 19:30–21:30 IST / 10:00–12:00 EST (Golden Overlap)
# Slot 5: Short #4 | 17:00–19:00 UTC | 22:30–00:30 IST / 13:00–15:00 EST (Bedtime / US Lunch)
# Slot 6: Short #5 | 21:00–23:00 UTC | 02:30–04:30 IST / 17:00–19:00 EST (US Evening)

SLOT_DEFINITIONS = [
    {"slot_id": 1, "is_short": True,  "name": "Short #1 (India Morning)",     "start_hour": 1,  "start_min": 30, "window_mins": 120},
    {"slot_id": 2, "is_short": True,  "name": "Short #2 (India Lunch)",       "start_hour": 7,  "start_min": 30, "window_mins": 120},
    {"slot_id": 3, "is_short": False, "name": "Long Video (Global Anchor)",   "start_hour": 11, "start_min": 30, "window_mins": 120},
    {"slot_id": 4, "is_short": True,  "name": "Short #3 (Golden Overlap)",   "start_hour": 14, "start_min": 0,  "window_mins": 120},
    {"slot_id": 5, "is_short": True,  "name": "Short #4 (US Lunch/IN Night)", "start_hour": 17, "start_min": 0,  "window_mins": 120},
    {"slot_id": 6, "is_short": True,  "name": "Short #5 (US Evening Peak)",   "start_hour": 21, "start_min": 0,  "window_mins": 120},
]

# ── Global State ──────────────────────────────────────────────────────────────
_SCHEDULE_CACHE: dict = {}
_EXECUTED_SLOTS: set = set()
_SCHEDULER_THREAD: threading.Thread | None = None
_SCHEDULER_LOCK = threading.Lock()
_LAST_HEARTBEAT: float = 0.0


def compute_daily_schedule(target_date: datetime.date = None) -> list[dict]:
    """
    Computes the 6 target slot trigger times for target_date (UTC).
    Uses a deterministic daily seed so trigger minutes remain consistent for the day
    across container restarts, but change randomly every day.
    """
    if target_date is None:
        target_date = datetime.datetime.now(datetime.timezone.utc).date()

    date_str = target_date.strftime("%Y-%m-%d")

    schedule = []
    for slot in SLOT_DEFINITIONS:
        slot_id = slot["slot_id"]

        # Deterministic seed for today's slot
        seed_val = f"nightloom-{date_str}-slot-{slot_id}"
        rng = random.Random(seed_val)
        offset_mins = rng.randint(0, slot["window_mins"] - 1)

        base_dt = datetime.datetime(
            target_date.year, target_date.month, target_date.day,
            slot["start_hour"], slot["start_min"],
            tzinfo=datetime.timezone.utc
        )
        trigger_dt = base_dt + datetime.timedelta(minutes=offset_mins)

        # Local time conversions for display
        ist_dt = trigger_dt.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        est_dt = trigger_dt.astimezone(datetime.timezone(datetime.timedelta(hours=-5)))

        unique_key = f"{date_str}-slot-{slot_id}"
        status = "Completed" if unique_key in _EXECUTED_SLOTS else "Pending"

        schedule.append({
            "unique_key": unique_key,
            "slot_id": slot_id,
            "is_short": slot["is_short"],
            "format_label": "🎬 Short" if slot["is_short"] else "🎞️ Long Video",
            "name": slot["name"],
            "trigger_dt": trigger_dt,
            "utc_str": trigger_dt.strftime("%H:%M UTC"),
            "ist_str": ist_dt.strftime("%I:%M %p IST"),
            "est_str": est_dt.strftime("%I:%M %p EST"),
            "status": status,
        })


    return schedule


def get_schedule_display_data() -> list[dict]:
    """Returns schedule formatted for display on the Gradio dashboard."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_schedule = compute_daily_schedule(now_utc.date())

    display_rows = []
    for s in today_schedule:
        display_rows.append({
            "Slot": f"Slot #{s['slot_id']}",
            "Format": s["format_label"],
            "Target Window / Name": s["name"],
            "Trigger Time (UTC)": s["utc_str"],
            "India Time (IST)": s["ist_str"],
            "US Time (EST)": s["est_str"],
            "Status": s["status"],
        })
    return display_rows


def _scheduler_loop():
    """Persistent 24/7 background loop keeping HF Space active & executing slots."""
    global _LAST_HEARTBEAT
    print("[scheduler] 🤖 24/7 Daily Auto-Pilot Engine started in background!")

    while True:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_ts = time.time()

            # Heartbeat every 5 minutes to keep HF Space alive
            if now_ts - _LAST_HEARTBEAT > 300:
                ts_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
                print(f"[scheduler] 💓 24/7 Heartbeat ({ts_str}) — Space active & operational.")
                _LAST_HEARTBEAT = now_ts

            # Evaluate today's schedule
            today_schedule = compute_daily_schedule(now_utc.date())

            for slot in today_schedule:
                unique_key = slot["unique_key"]
                trigger_dt = slot["trigger_dt"]

                # If trigger time has arrived and slot has not executed yet
                if now_utc >= trigger_dt and unique_key not in _EXECUTED_SLOTS:
                    print(f"\n=======================================================")
                    print(f"[scheduler] ⏰ SLOT TRIGGERED: {slot['name']} ({slot['utc_str']})")
                    print(f"=======================================================")

                    _EXECUTED_SLOTS.add(unique_key)
                    slot["status"] = "Running"

                    try:
                        print(f"[scheduler] Launching live pipeline (is_short={slot['is_short']}, style=pexels)...")
                        orchestrator.run_pipeline(
                            is_short=slot["is_short"],
                            upload=True,
                            privacy="public",
                            style="pexels",
                        )
                        slot["status"] = "Completed"
                        print(f"[scheduler] ✅ Slot {slot['slot_id']} completed successfully!")
                    except Exception as e:
                        slot["status"] = "Failed"
                        print(f"[scheduler] ❌ Slot {slot['slot_id']} failed: {e}")

        except Exception as e:
            print(f"[scheduler] Loop error: {e}")

        time.sleep(30)


def start_scheduler():
    """Starts the 24/7 background scheduler thread if not already running."""
    # Guarantee memory DB & Supabase cloud restore complete FIRST before scheduler runs
    memory.init_db()

    global _SCHEDULER_THREAD
    with _SCHEDULER_LOCK:
        if _SCHEDULER_THREAD is None or not _SCHEDULER_THREAD.is_alive():
            _SCHEDULER_THREAD = threading.Thread(target=_scheduler_loop, daemon=True)
            _SCHEDULER_THREAD.start()
            print("[scheduler] Background daemon thread launched.")



def trigger_next_slot_now(is_short: bool = True):
    """Fires an immediate test run of the scheduler pipeline."""
    print("[scheduler] ⚡ Immediate test trigger requested!")
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_schedule = compute_daily_schedule(now_utc.date())

    target_slot = today_schedule[0]
    for s in today_schedule:
        if s["unique_key"] not in _EXECUTED_SLOTS:
            target_slot = s
            break

    _EXECUTED_SLOTS.add(target_slot["unique_key"])
    print(f"[scheduler] 🚀 Triggering {target_slot['name']} live right now...")
    orchestrator.run_pipeline(
        is_short=is_short,
        upload=True,
        privacy="public",
        style="pexels",
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="24/7 Daily Auto-Pilot Scheduler")
    parser.add_argument("--trigger-now", action="store_true", help="Trigger an immediate slot run for testing")
    args = parser.parse_args()

    if args.trigger_now:
        trigger_next_slot_now(is_short=True)
    else:
        print("=== Daily 6-Slot Schedule Preview (Today) ===")
        sched = compute_daily_schedule()
        for s in sched:
            print(f"Slot {s['slot_id']} | {s['format_label']:<15} | {s['utc_str']:<10} | {s['ist_str']:<14} | {s['est_str']:<14} | {s['name']}")



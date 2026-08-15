"""24/7 Real-Time Auto-Pilot Engine for YT-Automation-Hosted."""

import datetime
import random
import threading
import time

from . import config, memory, orchestrator
from . import youtube_metrics, learning_engine

SLOT_DEFINITIONS = [
    {"slot_id": 1, "is_short": True,  "name": "Short #1 (India Morning)",     "start_hour": 1,  "start_min": 30, "window_mins": 120},
    {"slot_id": 2, "is_short": True,  "name": "Short #2 (India Lunch)",       "start_hour": 7,  "start_min": 30, "window_mins": 120},
    {"slot_id": 3, "is_short": False, "name": "Long Video (Global Anchor)",   "start_hour": 11, "start_min": 30, "window_mins": 120},
    {"slot_id": 4, "is_short": True,  "name": "Short #3 (Golden Overlap)",    "start_hour": 14, "start_min": 0,  "window_mins": 120},
    {"slot_id": 5, "is_short": True,  "name": "Short #4 (US Lunch/IN Night)", "start_hour": 17, "start_min": 0,  "window_mins": 120},
    {"slot_id": 6, "is_short": True,  "name": "Short #5 (US Evening Peak)",   "start_hour": 21, "start_min": 0,  "window_mins": 120},
]

_EXECUTED_SLOTS: set = set()
_SCHEDULER_THREAD: threading.Thread | None = None
_SCHEDULER_LOCK = threading.Lock()
_LAST_HEARTBEAT: float = 0.0
_LAST_LEARNING_DATE: str | None = None


def is_slot_completed(date_str: str, slot_id: int) -> bool:
    unique_key = f"{date_str}-slot-{slot_id}"
    if unique_key in _EXECUTED_SLOTS:
        return True
    try:
        with memory.get_conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM run_log WHERE decision = 'slot_trigger' AND reason = ?",
                (unique_key,),
            )
            if cur.fetchone()[0] > 0:
                _EXECUTED_SLOTS.add(unique_key)
                return True
    except Exception as e:
        print(f"[scheduler] DB slot check warning: {e}")
    return False


def compute_daily_schedule(target_date: datetime.date = None) -> list[dict]:
    if target_date is None:
        target_date = datetime.datetime.now(datetime.timezone.utc).date()
    date_str = target_date.strftime("%Y-%m-%d")
    schedule = []

    for slot in SLOT_DEFINITIONS:
        slot_id = slot["slot_id"]
        seed_val = f"nightloom-{date_str}-slot-{slot_id}"
        rng = random.Random(seed_val)
        offset_mins = rng.randint(0, slot["window_mins"] - 1)
        base_dt = datetime.datetime(
            target_date.year, target_date.month, target_date.day,
            slot["start_hour"], slot["start_min"], tzinfo=datetime.timezone.utc,
        )
        trigger_dt = base_dt + datetime.timedelta(minutes=offset_mins)
        ist_dt = trigger_dt.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        est_dt = trigger_dt.astimezone(datetime.timezone(datetime.timedelta(hours=-5)))
        unique_key = f"{date_str}-slot-{slot_id}"
        completed = is_slot_completed(date_str, slot_id)
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
            "status": "Completed" if completed else "Pending",
        })
    return schedule


def get_schedule_display_data() -> list[dict]:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return [
        {
            "Slot": f"Slot #{s['slot_id']}",
            "Format": s["format_label"],
            "Target Window / Name": s["name"],
            "Trigger Time (UTC)": s["utc_str"],
            "India Time (IST)": s["ist_str"],
            "US Time (EST)": s["est_str"],
            "Status": s["status"],
        }
        for s in compute_daily_schedule(now_utc.date())
    ]


def _run_daily_learning_cycle(date_str: str):
    """Run telemetry + learning once per UTC day; failures never stop uploads."""
    global _LAST_LEARNING_DATE
    if _LAST_LEARNING_DATE == date_str:
        return
    try:
        print("[scheduler] 🧠 Running daily closed-loop learning cycle ...")
        youtube_metrics.collect_due_snapshots()
        learning_engine.learn_once()
        _LAST_LEARNING_DATE = date_str
    except Exception as e:
        print(f"[scheduler] Learning cycle warning (production unaffected): {e}")


def _scheduler_loop():
    global _LAST_HEARTBEAT
    print("[scheduler] 🤖 24/7 Daily Auto-Pilot Engine started in background!")

    while True:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_ts = time.time()
            date_str = now_utc.strftime("%Y-%m-%d")

            if now_ts - _LAST_HEARTBEAT > 300:
                ts_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
                print(f"[scheduler] 💓 24/7 Heartbeat ({ts_str}) — Space active & operational.")
                _LAST_HEARTBEAT = now_ts

            # Learning is strictly observational first: it reads mature
            # published performance and updates policy state. It cannot block
            # or alter the production pipeline.
            _run_daily_learning_cycle(date_str)

            today_schedule = compute_daily_schedule(now_utc.date())
            for slot in today_schedule:
                unique_key = slot["unique_key"]
                trigger_dt = slot["trigger_dt"]
                if now_utc >= trigger_dt and not is_slot_completed(date_str, slot["slot_id"]):
                    print("\n=======================================================")
                    print(f"[scheduler] ⏰ SLOT TRIGGERED: {slot['name']} ({slot['utc_str']})")
                    print("=======================================================")
                    _EXECUTED_SLOTS.add(unique_key)
                    try:
                        with memory.get_conn() as conn:
                            memory.log_run_start(conn, decision="slot_trigger", reason=unique_key)
                    except Exception:
                        pass

                    try:
                        print(f"[scheduler] Launching live pipeline (is_short={slot['is_short']}, style=pexels)...")
                        orchestrator.run_pipeline(
                            is_short=slot["is_short"],
                            upload=True,
                            privacy="public",
                            style="pexels",
                        )
                        print(f"[scheduler] ✅ Slot {slot['slot_id']} completed successfully!")
                    except Exception as e:
                        print(f"[scheduler] ❌ Slot {slot['slot_id']} failed: {e}")
        except Exception as e:
            print(f"[scheduler] Loop error: {e}")

        time.sleep(30)


def start_scheduler():
    memory.init_db()
    global _SCHEDULER_THREAD
    with _SCHEDULER_LOCK:
        if _SCHEDULER_THREAD is None or not _SCHEDULER_THREAD.is_alive():
            _SCHEDULER_THREAD = threading.Thread(target=_scheduler_loop, daemon=True)
            _SCHEDULER_THREAD.start()
            print("[scheduler] Background daemon thread launched.")


def trigger_next_slot_now(is_short: bool = True):
    print("[scheduler] ⚡ Immediate test trigger requested!")
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_schedule = compute_daily_schedule(now_utc.date())
    target_slot = next((s for s in today_schedule if s["unique_key"] not in _EXECUTED_SLOTS), today_schedule[0])
    _EXECUTED_SLOTS.add(target_slot["unique_key"])
    print(f"[scheduler] 🚀 Triggering {target_slot['name']} live right now...")
    orchestrator.run_pipeline(is_short=is_short, upload=True, privacy="public", style="pexels")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="24/7 Daily Auto-Pilot Scheduler")
    parser.add_argument("--trigger-now", action="store_true")
    args = parser.parse_args()
    if args.trigger_now:
        trigger_next_slot_now(is_short=True)
    else:
        print("=== Daily 6-Slot Schedule Preview (Today) ===")
        for s in compute_daily_schedule():
            print(f"Slot {s['slot_id']} | {s['format_label']:<15} | {s['utc_str']:<10} | {s['ist_str']:<14} | {s['est_str']:<14} | {s['name']}")

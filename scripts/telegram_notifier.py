"""
telegram_notifier.py — Hosted No-Op Stub for Hugging Face Spaces.

Telegram notifications are completely disabled on HF Spaces (the web UI
dashboard handles all pipeline interaction and live logs).
"""

def notify(text: str, parse_mode: str = "Markdown") -> bool:
    return False

def create_live_progress_card(video_id: int, title: str = None):
    return None

def update_live_progress(video_id: int, stage_num: str, stage_name: str, percent: int, log_line: str = None, force: bool = False):
    pass

def send_stage_start(stage_num: str, stage_name: str, video_id: int):
    pass

def send_stage_complete(stage_num: str, stage_name: str, video_id: int):
    pass

def send_completion_card(video_id: int, title: str, youtube_url: str = None):
    pass

def send_error_alert(stage_num: str, stage_name: str, video_id: int, error_msg: str):
    pass

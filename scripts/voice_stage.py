"""
voice_stage.py — takes a video row in 'scripted' status, generates its
audio, transcribes word-level timestamps, and saves both — advancing
the video to 'voiced' status, ready for the visuals stage.
"""

import json
from pathlib import Path

from . import memory as mem
from . import tts
from . import captions
from . import config


def process_video(video_id, conn=None, voice=tts.DEFAULT_VOICE):
    if conn is None:
        with mem.get_conn() as c:
            return process_video(video_id, conn=c, voice=voice)

    row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if row is None:
        raise ValueError(f"No video with id {video_id}")
    if row["status"] != "scripted":
        print(f"[voice_stage] video {video_id} is in status '{row['status']}', not 'scripted' — skipping.")
        return

    script = json.loads(row["script_json"])

    audio_path = config.ASSETS_DIR / "audio" / f"video_{video_id}.mp3"
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[voice_stage] Generating audio for video {video_id}...")
    _, segments_text = tts.generate_audio(script, audio_path, voice=voice)

    print(f"[voice_stage] Transcribing timestamps for video {video_id}...")
    words = captions.transcribe_with_timestamps(audio_path)
    segment_map = captions.map_words_to_segments(words, segments_text)

    timestamps_path = config.ASSETS_DIR / "audio" / f"video_{video_id}_timestamps.json"
    with open(timestamps_path, "w") as f:
        json.dump(segment_map, f, indent=2)

    mem.update_video_status(conn, video_id, "voiced", audio_path=str(audio_path))
    print(f"[voice_stage] video {video_id} -> voiced. Audio: {audio_path}, timestamps: {timestamps_path}")


def process_all_pending(voice=tts.DEFAULT_VOICE):
    """Processes every video currently in 'scripted' status."""
    mem.init_db()
    with mem.get_conn() as conn:
        rows = conn.execute("SELECT video_id FROM videos WHERE status = 'scripted'").fetchall()
        video_ids = [r["video_id"] for r in rows]

    if not video_ids:
        print("[voice_stage] No videos pending voice generation.")
        return

    print(f"[voice_stage] Processing {len(video_ids)} pending video(s): {video_ids}")
    for vid in video_ids:
        with mem.get_conn() as conn:
            try:
                process_video(vid, conn=conn, voice=voice)
            except Exception as e:
                import traceback
                traceback.print_exc()
                mem.update_video_status(conn, vid, "failed", error_message=str(e))
                print(f"[voice_stage] video {vid} FAILED: {e}")
                raise



def main():
    import argparse
    parser = argparse.ArgumentParser(description="Voice generation stage")
    parser.add_argument("--video", type=int, default=None, help="Process a specific video ID")
    args = parser.parse_args()

    mem.init_db()
    if args.video:
        process_video(args.video)
    else:
        process_all_pending()


if __name__ == "__main__":
    main()

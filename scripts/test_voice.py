"""
test_voice.py — test script & voiceover generation with Night Loom channel branding.
"""

import json
from pathlib import Path
from . import memory as mem
from . import decision_engine as de
from . import script_generator as sg
from . import voice_stage

def run_test():
    mem.init_db()
    with mem.get_conn() as conn:
        print("[test_voice] Deciding video concept ...")
        decision = de.decide_next_video(conn)

        print("[test_voice] Generating script with Night Loom channel branding ...")
        script = sg.generate_script(decision, is_short=True)

        video_id = mem.create_video(
            conn,
            category=decision["category"],
            format_="short",
            style="A",
            title=script["title"],
            hook_line=script["hook_line"],
            ending_line=script["ending_line"],
            cta=script["cta"],
            script_json=script,
        )

    print("\n=======================================================")
    print(f"NEW SCRIPT GENERATED (Video ID: {video_id})")
    print(f"=======================================================")
    print(f"Title      : {script.get('title')}")
    print(f"Hook Line  : {script.get('hook_line')}")
    print(f"Intro Line : {script.get('intro_line')}")
    print(f"Scenes     : {len(script.get('scenes', []))} beats")
    print("-------------------------------------------------------")
    print(json.dumps(script, indent=2))
    print("=======================================================\n")

    print(f"[test_voice] Generating voice narration & Whisper timestamps for Video {video_id} ...")
    voice_stage.process_video(video_id)

    audio_file = Path("assets/audio") / f"video_{video_id}.mp3"
    timestamps_file = Path("assets/audio") / f"video_{video_id}_timestamps.json"

    print("\n=======================================================")
    print(f"VOICE GENERATION COMPLETE!")
    print(f"  Audio File      : {audio_file.resolve()}")
    print(f"  Timestamps File : {timestamps_file.resolve()}")
    print(f"=======================================================\n")

    return video_id

if __name__ == "__main__":
    run_test()

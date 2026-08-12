"""
orchestrator.py — Master End-to-End Pipeline Orchestrator.

One command executes the complete YouTube Shorts creation & publishing pipeline:
  1. Decision & Script Generation  (decision_engine + script_generator)
  2. Story Bible Fact Extraction   (fact_extractor + memory)
  3. Audio TTS & Whisper Captions  (voice_stage)
  4. SDXL AI Visuals & Pexels Clips (visuals_stage)
  5. SadTalker Animated Avatar     (avatar_stage)
  6. 9:16 Video Compositing        (composite_stage)
  7. SDXL High-CTR Thumbnail       (thumbnail_stage)
  8. LLM Metadata & YouTube Upload (upload_stage)

Usage:
  python -m scripts.orchestrator [--no-upload] [--privacy {private,unlisted,public}]
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import memory as mem
from . import decision_engine as de
from . import script_generator as sg
from . import fact_extractor as fe
from . import config
from . import telegram_notifier as tn


def _run_stage_subprocess(module: str, video_id: int, extra_args: list[str] | None = None, stage_num: str = "1", label: str = ""):
    """
    Runs a pipeline stage module in an isolated Python process, streaming stdout live
    both to the terminal and to the Telegram live progress card.
    """
    import re
    cmd = [sys.executable, "-u", "-m", module, "--video", str(video_id)]
    if extra_args:
        cmd.extend(extra_args)
    print(f"[orchestrator] Spawning background subprocess: {' '.join(cmd[3:])}")
    creationflags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)

    proc = subprocess.Popen(
        cmd,
        cwd=str(config.PROJECT_ROOT),
        creationflags=creationflags,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


    base_pct = int((int(stage_num) - 1) / 7.0 * 100) if stage_num.isdigit() else 0
    current_pct = base_pct

    if proc.stdout:
        for line in iter(proc.stdout.readline, ""):
            print(line, end="", flush=True)

            pct_match = re.search(r"(\d{1,3})%", line)
            shot_match = re.search(r"(\d+)/(\d+)", line)
            if pct_match:
                val = int(pct_match.group(1))
                if 0 <= val <= 100:
                    current_pct = base_pct + int(val / 7.0)
            elif shot_match:
                cur_shot, tot_shot = int(shot_match.group(1)), int(shot_match.group(2))
                if tot_shot > 0:
                    current_pct = base_pct + int((cur_shot / float(tot_shot)) * 14.0)

            tn.update_live_progress(video_id, stage_num, label, min(99, max(0, current_pct)), log_line=line)

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Stage {module} failed (exit {proc.returncode})")
    print(f"[orchestrator] Stage {module} completed cleanly. Resting GPU 3s ...")
    time.sleep(3)


def _cleanup_intermediate_assets(video_id: int):
    """Deletes all generated assets for video_id from assets/images, assets/audio, assets/visuals, output, assets/video, and temp."""
    print(f"[orchestrator] Cleaning up all generated assets for video {video_id} ...")

    # 1. assets/images (video_N_bg_*.png, video_N_thumbnail.png, etc.)
    img_dir = config.ASSETS_DIR / "images"
    if img_dir.exists():
        for p in img_dir.glob(f"video_{video_id}*"):
            p.unlink(missing_ok=True)

    # 2. assets/audio (video_N.mp3, video_N_timestamps.json)
    audio_dir = config.ASSETS_DIR / "audio"
    if audio_dir.exists():
        for p in audio_dir.glob(f"video_{video_id}*"):
            p.unlink(missing_ok=True)

    # 3. assets/visuals (video_N_manifest.json, video_N_subtitles.ass)
    visuals_dir = config.ASSETS_DIR / "visuals"
    if visuals_dir.exists():
        for p in visuals_dir.glob(f"video_{video_id}*"):
            p.unlink(missing_ok=True)

    # 4. output (video_N.mp4)
    out_dir = config.OUTPUT_DIR
    if out_dir.exists():
        for p in out_dir.glob(f"video_{video_id}*"):
            p.unlink(missing_ok=True)

    # 5. assets/video (video_N_avatar.mp4)
    v_dir = config.ASSETS_DIR / "video"
    if v_dir.exists():
        for p in v_dir.glob(f"video_{video_id}*"):
            p.unlink(missing_ok=True)

    # 6. SadTalker tmp audio & results
    sadtalker_dir = config.PROJECT_ROOT / "models" / "sadtalker"
    wav_file = sadtalker_dir / "tmp_audio" / f"video_{video_id}.wav"
    wav_file.unlink(missing_ok=True)
    res_dir = sadtalker_dir / "results" / f"video_{video_id}"
    if res_dir.exists():
        shutil.rmtree(res_dir, ignore_errors=True)

    # 7. Temp working dir
    temp_dir = config.PROJECT_ROOT / "temp"
    if temp_dir.exists():
        for p in temp_dir.glob(f"*video_{video_id}*"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)

    print(f"[orchestrator] Asset cleanup complete: folders emptied for video {video_id}!")


def run_pipeline(video_id: int | None = None, is_short: bool = True, upload: bool = True, privacy: str = "public", style: str | None = None):
    """
    Runs the complete video automation pipeline for a single video.
    If video_id is provided, runs remaining stages for that video.
    Otherwise, generates a brand new video from scratch.
    """
    mem.init_db()

    # Step 1: Script & Story Bible Generation (if creating new video)
    if video_id is None:
        with mem.get_conn() as conn:
            decision = de.decide_next_video(conn)
            run_id = mem.log_run_start(conn, decision["action"], decision["reason"])
            print(f"\n=======================================================")
            print(f"[STAGE 1/7] Decision: {decision['action']} — {decision['reason']}")
            print(f"=======================================================")

            series = None
            series_id = decision.get("series_id")
            if series_id:
                series = mem.get_series(conn, series_id)

            try:
                script = sg.generate_script(decision, series=series, is_short=is_short)
                print(f"[orchestrator] Script generated: \"{script['title']}\"")

                format_ = "short" if is_short else "long_continuous"

                video_id = mem.create_video(
                    conn,
                    category=decision["category"],
                    format_=format_,
                    style="A",
                    series_id=series_id,
                    series_part=(series["current_part"] + 1) if series else None,
                    title=script["title"],
                    hook_line=script["hook_line"],
                    ending_line=script["ending_line"],
                    cta=script["cta"],
                    script_json=script,
                )
                print(f"[orchestrator] Video entry created: video_id={video_id}")

                if decision["action"] in ("continue_series", "conclude_series"):
                    is_conclusion = decision["action"] == "conclude_series"
                    facts = fe.extract_facts(script, is_conclusion=is_conclusion)
                    mem.update_series_state(
                        conn, series_id,
                        canon_facts=facts["new_canon_facts"],
                        characters=facts["character_updates"],
                        unresolved_threads=facts["unresolved_threads"],
                        last_episode_summary=facts["episode_summary"],
                        status="concluded" if is_conclusion else "active",
                        bump_part=True,
                    )
                elif decision["action"] == "new_content" and decision.get("start_new_series"):
                    new_series_id = mem.create_series(
                        conn,
                        series_name=script["title"],
                        category=decision["category"],
                        format_="long_continuous" if not is_short else "short",
                    )
                    facts = fe.extract_facts(script, is_conclusion=False)
                    mem.update_series_state(
                        conn, new_series_id,
                        canon_facts=facts["new_canon_facts"],
                        characters=facts["character_updates"],
                        unresolved_threads=facts["unresolved_threads"],
                        last_episode_summary=facts["episode_summary"],
                        bump_part=True,
                    )
                    conn.execute(
                        "UPDATE videos SET series_id = ?, series_part = 1 WHERE video_id = ?",
                        (new_series_id, video_id),
                    )

                mem.log_run_finish(conn, run_id, "success", video_id=video_id)

            except Exception as e:
                mem.log_run_finish(conn, run_id, "failed")
                print(f"[orchestrator] Stage 1 failed: {e}")
                raise

    # Status-aware stage runner — skips stages already completed
    STATUS_ORDER = ["scripted", "voiced", "visualized", "rendered", "thumbnail_done", "uploaded"]

    def _already_done(required_status: str) -> bool:
        """Returns True if the video's current DB status is at or past required_status."""
        with mem.get_conn() as conn:
            row = conn.execute("SELECT status FROM videos WHERE video_id = ?", (video_id,)).fetchone()
            current = row["status"] if row else "scripted"
        try:
            return STATUS_ORDER.index(current) >= STATUS_ORDER.index(required_status)
        except ValueError:
            return False

    def _run_stage(stage_num: str, label: str, module: str, required_done_status: str, extra_args=None):
        """Skips stage if already done, otherwise runs it in an isolated subprocess."""
        if _already_done(required_done_status):
            print(f"\n[STAGE {stage_num}/7] {label} already complete for video {video_id} — skipping.")
            return
        print(f"\n[STAGE {stage_num}/7] Running {label} for video {video_id} ... (isolated subprocess)")
        tn.send_stage_start(stage_num, label, video_id)
        try:
            _run_stage_subprocess(module, video_id, extra_args, stage_num=stage_num, label=label)
            tn.send_stage_complete(stage_num, label, video_id)
        except RuntimeError as e:
            tn.send_error_alert(stage_num, label, video_id, str(e))
            print(f"[orchestrator] Stage {stage_num} ({label}) FAILED: {e}")
            print(f"[orchestrator] TIP: Re-run with --video {video_id} to resume from this stage.")
            raise

    # Step 2: Voice & Captioning Stage (TTS + Whisper) — GPU: Whisper
    _run_stage("2", "Voice & Captioning", "scripts.voice_stage", "voiced")

    # Step 3: Visuals Stage (SDXL Background Images) — GPU: SDXL ~6 GB
    visual_args = ["--style", style] if style else None
    _run_stage("3", "Visuals/SDXL", "scripts.visuals_stage", "visualized", extra_args=visual_args)

    # Step 4: Avatar Stage (SadTalker / Wav2Lip) — GPU: Wav2Lip
    avatar_clip_path = config.ASSETS_DIR / "video" / f"video_{video_id}_avatar.mp4"
    if avatar_clip_path.exists() or _already_done("rendered"):
        print(f"\n[STAGE 4/7] Avatar stage already complete for video {video_id} — skipping.")
    else:
        print(f"\n[STAGE 4/7] Running Avatar Stage for video {video_id} ... (isolated subprocess)")
        tn.send_stage_start("4", "Avatar Stage", video_id)
        try:
            _run_stage_subprocess("scripts.avatar_stage", video_id, stage_num="4", label="Avatar Stage")
            tn.send_stage_complete("4", "Avatar Stage", video_id)
        except RuntimeError as e:
            tn.send_error_alert("4", "Avatar Stage", video_id, str(e))
            print(f"[orchestrator] Stage 4 (Avatar) FAILED: {e}")
            print(f"[orchestrator] TIP: Re-run with --video {video_id} to resume from this stage.")
            raise

    # Step 5: Video Compositing (FFmpeg, CPU) — no GPU needed
    _run_stage("5", "Video Compositing", "scripts.composite_stage", "rendered")

    # Step 6: Thumbnail (SDXL) — GPU: SDXL ~6 GB
    _run_stage("6", "Thumbnail/SDXL", "scripts.thumbnail_stage", "thumbnail_done")

    # Step 7: YouTube Upload (LLM metadata + API) — CPU only
    if _already_done("uploaded"):
        print(f"\n[STAGE 7/7] Video {video_id} already uploaded — skipping.")
    elif upload:
        print(f"\n[STAGE 7/7] Running LLM Metadata & YouTube Auto-Upload for video {video_id} (privacy: {privacy}) ...")
        try:
            _run_stage_subprocess("scripts.upload_stage", video_id, ["--privacy", privacy], stage_num="7", label="YouTube Upload")

            with mem.get_conn() as conn:
                row = conn.execute("SELECT title, youtube_video_id FROM videos WHERE video_id = ?", (video_id,)).fetchone()
                yt_id = row["youtube_video_id"] if row and row["youtube_video_id"] else None
                video_title = row["title"] if row else f"video_{video_id}"
                yt_url = f"https://youtu.be/{yt_id}" if yt_id else None

            tn.send_completion_card(video_id, video_title, yt_url)
            _cleanup_intermediate_assets(video_id)
        except RuntimeError as e:
            print(f"[orchestrator] Stage 7 (Upload) FAILED: {e}")
            print(f"[orchestrator] TIP: Re-run with --video {video_id} --privacy {privacy} to retry upload only.")
            raise
    else:
        print(f"\n[STAGE 7/7] YouTube upload skipped (--no-upload flag set).")

    print(f"\nPIPELINE COMPLETE FOR VIDEO {video_id}!")
    print(f"  Final Video : output/video_{video_id}.mp4")
    print(f"  Thumbnail   : assets/images/video_{video_id}_thumbnail.png")

    return video_id


def main():
    parser = argparse.ArgumentParser(description="Master End-to-End YT Automation Pipeline")
    parser.add_argument("--video", type=int, default=None, help="Run pipeline for an existing video ID")
    parser.add_argument("--long", action="store_true", help="Generate long-form video instead of Shorts")
    parser.add_argument("--style", type=str, default=None, choices=["sdxl", "pexels"], help="Override background visual style (sdxl or pexels)")
    parser.add_argument("--no-upload", action="store_true", help="Skip auto-uploading to YouTube")
    parser.add_argument("--privacy", type=str, default="public", choices=["private", "unlisted", "public"], help="YouTube privacy status (default: public)")
    args = parser.parse_args()

    run_pipeline(
        video_id=args.video,
        is_short=not args.long,
        upload=not args.no_upload,
        privacy=args.privacy,
        style=args.style,
    )


if __name__ == "__main__":
    main()

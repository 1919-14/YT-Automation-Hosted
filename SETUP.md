# YT Automation — Setup

## 1. Install core deps (run this on your machine, not here)

```bash
cd yt-automation
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Verify config loads

```bash
python3 -m scripts.config
```
Should print your provider/base URL/model and a masked API key.

## 3. Test the live LLM connection

```bash
python3 -m scripts.llm_client
```
Should print `Response: pipeline online` (or close to it — models
sometimes ignore exact-string instructions).

If this fails, check:
- `.env` has the correct `LLM_BASE_URL` and `LLM_API_KEY`
- The OpenCode Zen model name in `.env` (`LLM_MODEL`) matches what
  their API expects — check their docs/dashboard for the exact
  model string (e.g. it might be `deepseek/deepseek-v4` or similar,
  not just `deepseek-v4`)

## 4. Test the memory layer

```bash
python3 -m scripts.memory
```
Should print `Database ready at .../data/memory.db`.

## 5. Run the full script-generation loop (decision -> script -> memory)

```bash
python -m scripts.orchestrator          # short-form video
python -m scripts.orchestrator --long   # long-form video
```

This will: decide what to make (new/continue/conclude), call the LLM
to write a full script, save it to the database, and (for series)
extract facts back into the story bible. Run it several times in a
row — the DB starts empty, so early runs will mostly be "new_content"
until series start accumulating. Try running it ~10-15 times to see
a series actually get created, continued, and eventually concluded.

To inspect what's in the database at any point:
```bash
python -c "from scripts import memory as mem; import json
with mem.get_conn() as conn:
    for row in conn.execute('SELECT video_id, title, category, series_id, series_part FROM videos'):
        print(dict(row))"
```

## 6. Generate voice + captions for pending videos

```bash
python -m scripts.voice_stage
```
Processes every video currently in 'scripted' status: generates
narration audio (Edge-TTS, free, no key needed) and word-level
timestamps (faster-whisper, runs locally on your RTX 4050).

**GPU note**: faster-whisper on Windows has a known, somewhat finicky
issue where `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` doesn't
always put the DLLs on Windows' library search path automatically, even
though the packages install fine. Rather than fight that right now,
`WHISPER_DEVICE=cpu` is the default in `.env` — CPU is plenty fast for
short-form audio (under a minute). It'll be slower for full 15-minute
long-form transcription, so once short-form is confirmed working end
to end, we can circle back and properly debug the CUDA DLL path (likely
fix: manually add the venv's `Lib\site-packages\nvidia\cublas\bin` and
`...\cudnn\bin` folders to PATH, or set `WHISPER_DEVICE=cuda` in `.env`
after that's sorted).

First run downloads the whisper model (small, one-time, needs internet).

Check output:
```powershell
python -c "from scripts import memory as mem
with mem.get_conn() as conn:
    for row in conn.execute(\"SELECT video_id, status, audio_path FROM videos WHERE status='voiced'\"):
        print(dict(row))"
```

Listen to a generated file (`assets/audio/video_N.mp3`) and check the
matching `assets/audio/video_N_timestamps.json` for per-segment timing.
Watch the console for `[captions] WARNING` about word-count drift —
if you see it often, let me know and we'll make the alignment more
robust (fuzzy matching instead of pure word-count).

## Project status so far

- [x] Folder structure
- [x] SQLite schema (series, videos, run_log)
- [x] Memory access layer (scripts/memory.py) — tested end-to-end
- [x] Config loader (scripts/config.py) — reads .env
- [x] LLM client wrapper (scripts/llm_client.py) — verified live
- [x] Category config (scripts/categories.py)
- [x] Decision engine (scripts/decision_engine.py) — rule-based path tested, LLM judgment path needs live test
- [x] Script generator (scripts/script_generator.py) — prompts verified, needs live test
- [x] Fact extractor (scripts/fact_extractor.py) — verified live, working well
- [x] Orchestrator (scripts/orchestrator.py) — verified live, working well
- [x] TTS (scripts/tts.py) — Edge-TTS, needs live test
- [x] Captions (scripts/captions.py) — faster-whisper + segment alignment, needs live test
- [x] Voice stage wrapper (scripts/voice_stage.py) — ties TTS + captions to DB status
- [ ] Captions (faster-whisper)
- [ ] Visual pipeline A (SDXL-Turbo)
- [ ] Visual pipeline B (Pexels stock)
- [ ] Visual pipeline C (avatar + Wav2Lip)
- [ ] Video assembly (ffmpeg)
- [ ] Thumbnail generation
- [ ] YouTube upload (Data API v3)
- [ ] Orchestrator (ties it all together)

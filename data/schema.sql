-- ============================================================
-- YT Automation — Persistent Memory Schema
-- ============================================================

-- One row per ongoing or concluded story series.
-- This is the "story bible" that keeps continuations consistent
-- without ever re-feeding raw past scripts to the LLM.
CREATE TABLE IF NOT EXISTS series (
    series_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    series_name     TEXT NOT NULL,
    category        TEXT NOT NULL,              -- horror, facts, motivational, mystery, etc.
    format          TEXT NOT NULL,               -- short | long_continuous | long_compilation
    status          TEXT NOT NULL DEFAULT 'active',  -- active | concluded | on_hold
    current_part    INTEGER NOT NULL DEFAULT 0,
    total_parts_planned INTEGER,                 -- nullable = open-ended
    canon_facts     TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
    characters      TEXT NOT NULL DEFAULT '{}',   -- JSON object: {name: {role, traits, status}}
    unresolved_threads TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    last_episode_summary TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_video_date TEXT
);

-- One row per generated video (whether standalone or part of a series).
CREATE TABLE IF NOT EXISTS videos (
    video_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id       INTEGER REFERENCES series(series_id),  -- NULL if standalone
    series_part     INTEGER,                     -- part number within series, NULL if standalone
    category        TEXT NOT NULL,
    format          TEXT NOT NULL,                -- short | long_continuous | long_compilation
    style           TEXT NOT NULL,                -- A (ai_images) | B (stock) | C (avatar)
    title           TEXT,
    hook_line       TEXT,
    ending_line     TEXT,
    cta             TEXT,
    script_json     TEXT,                         -- full structured script, JSON
    script_hash     TEXT,                         -- to detect near-duplicate content
    audio_path      TEXT,
    visual_manifest_path TEXT,               -- path to video_N_manifest.json
    video_path       TEXT,
    thumbnail_path  TEXT,
    youtube_video_id TEXT,
    status          TEXT NOT NULL DEFAULT 'pending', -- pending | scripted | voiced | visualized | assembled | uploaded | failed
    error_message   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    uploaded_at     TEXT
);

-- Simple run log for the orchestrator — helpful for debugging automated runs.
CREATE TABLE IF NOT EXISTS run_log (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    decision        TEXT,        -- continue_series | conclude_series | new_content
    reason          TEXT,
    video_id        INTEGER REFERENCES videos(video_id),
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    status          TEXT DEFAULT 'running'  -- running | success | failed
);

CREATE INDEX IF NOT EXISTS idx_series_status ON series(status);
CREATE INDEX IF NOT EXISTS idx_videos_series ON videos(series_id);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);

-- ============================================================
-- YT Automation — Persistent Memory Schema
-- ============================================================

CREATE TABLE IF NOT EXISTS series (
    series_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    series_name     TEXT NOT NULL,
    category        TEXT NOT NULL,
    format          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    current_part    INTEGER NOT NULL DEFAULT 0,
    total_parts_planned INTEGER,
    canon_facts     TEXT NOT NULL DEFAULT '[]',
    characters      TEXT NOT NULL DEFAULT '{}',
    unresolved_threads TEXT NOT NULL DEFAULT '[]',
    last_episode_summary TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_video_date TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    video_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id       INTEGER REFERENCES series(series_id),
    series_part     INTEGER,
    category        TEXT NOT NULL,
    format          TEXT NOT NULL,
    style           TEXT NOT NULL,
    title           TEXT,
    hook_line       TEXT,
    ending_line     TEXT,
    cta             TEXT,
    script_json     TEXT,
    script_hash     TEXT,
    audio_path      TEXT,
    visual_manifest_path TEXT,
    video_path       TEXT,
    thumbnail_path  TEXT,
    youtube_video_id TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    error_message   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    uploaded_at     TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    decision        TEXT,
    reason          TEXT,
    video_id        INTEGER REFERENCES videos(video_id),
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    status          TEXT DEFAULT 'running'
);

-- Closed-loop learning telemetry. Snapshots are append-only observations of
-- cumulative YouTube counters at a known video age.
CREATE TABLE IF NOT EXISTS video_metrics (
    metric_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        INTEGER NOT NULL REFERENCES videos(video_id),
    youtube_video_id TEXT NOT NULL,
    snapshot_label  TEXT NOT NULL,       -- 24h | 48h
    age_hours       REAL NOT NULL,
    views           INTEGER NOT NULL DEFAULT 0,
    likes           INTEGER NOT NULL DEFAULT 0,
    comments        INTEGER NOT NULL DEFAULT 0,
    collected_at    TEXT NOT NULL,
    UNIQUE(video_id, snapshot_label)
);

-- Learned reward per category/format. The learner updates this from mature
-- snapshots; the decision engine uses it as a soft bias, never as a hard rule.
CREATE TABLE IF NOT EXISTS learning_state (
    state_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    format          TEXT NOT NULL,
    sample_count    INTEGER NOT NULL DEFAULT 0,
    mean_reward     REAL NOT NULL DEFAULT 0.0,
    mean_views      REAL NOT NULL DEFAULT 0.0,
    mean_like_rate  REAL NOT NULL DEFAULT 0.0,
    updated_at      TEXT NOT NULL,
    UNIQUE(category, format)
);

CREATE INDEX IF NOT EXISTS idx_series_status ON series(status);
CREATE INDEX IF NOT EXISTS idx_videos_series ON videos(series_id);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_metrics_video ON video_metrics(video_id);
CREATE INDEX IF NOT EXISTS idx_metrics_snapshot ON video_metrics(snapshot_label);
CREATE INDEX IF NOT EXISTS idx_learning_category_format ON learning_state(category, format);

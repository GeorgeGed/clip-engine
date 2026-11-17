CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  vod_url TEXT NOT NULL,
  clips_wanted INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
  stage TEXT,
  message TEXT,
  progress REAL,
  vod_title TEXT,
  channel TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE INDEX jobs_created_at ON jobs (created_at DESC);

CREATE TABLE clips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
  n INTEGER NOT NULL,
  title TEXT,
  emoji TEXT,
  keyword TEXT,
  subject TEXT,
  score REAL,
  duration REAL,
  vod_start REAL,
  video_key TEXT NOT NULL,
  preview_key TEXT,
  thumb_key TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (job_id, n)
);

CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
  at TEXT NOT NULL,
  stage TEXT,
  message TEXT
);

CREATE INDEX events_job ON events (job_id, id);

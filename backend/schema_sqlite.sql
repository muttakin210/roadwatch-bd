-- Prototype schema (SQLite). Production schema for Postgres/Supabase: schema.sql (PLAN §8.3).
CREATE TABLE IF NOT EXISTS videos(
  id TEXT PRIMARY KEY, user_id TEXT, storage_key TEXT NOT NULL, content_hash TEXT, perceptual_hash TEXT,
  duration_s REAL, fps REAL, width INT, height INT, orientation TEXT, camera_type TEXT,
  lat REAL, lng REAL, place_name TEXT, location_source TEXT, recorded_at TEXT,
  status TEXT, moderation_status TEXT, consent_training INT, hints TEXT,
  created_at REAL, raw_deleted_at REAL);
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, video_id TEXT, model_version TEXT, rules_version TEXT, attempt INT,
  started_at REAL, finished_at REAL, error TEXT, progress REAL);
CREATE TABLE IF NOT EXISTS results(
  video_id TEXT, job_id TEXT, annotated_key TEXT, report_key TEXT, congestion_avg REAL,
  camera_motion_class TEXT, scene_summary TEXT);
CREATE TABLE IF NOT EXISTS events(
  id TEXT PRIMARY KEY, video_id TEXT, job_id TEXT, type TEXT, subtype TEXT, vehicle_class TEXT, track_id INT,
  start_s REAL, end_s REAL, raw_score REAL, confidence REAL, severity TEXT, reason TEXT,
  details TEXT, snapshot_key TEXT, verified INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS event_feedback(
  id TEXT PRIMARY KEY, event_id TEXT, user_id TEXT, verdict TEXT, corrected_type TEXT, note TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, video_id TEXT, reason TEXT, created_at REAL);
CREATE INDEX IF NOT EXISTS events_job ON events(job_id);

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
-- Accounts, verified reports and the reward ledger (backend/accounts.py).
-- Privacy defaults are all "hidden": a new user is anonymous until they opt in.
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, display_name TEXT NOT NULL,
  phone TEXT, role TEXT NOT NULL DEFAULT 'user',
  show_name INT NOT NULL DEFAULT 0, profile_public INT NOT NULL DEFAULT 0,
  share_contact INT NOT NULL DEFAULT 0, show_locations INT NOT NULL DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at REAL, expires_at REAL);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
-- One case per AI event. status: submitted -> confirmed | rejected (reviewer) -> fined | dismissed (police)
CREATE TABLE IF NOT EXISTS cases(
  id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, video_id TEXT NOT NULL, uploader_id TEXT NOT NULL,
  status TEXT NOT NULL, uploader_note TEXT, created_at REAL,
  reviewer_id TEXT, review_note TEXT, reviewed_at REAL,
  police_id TEXT, police_ref TEXT, fine_bdt INT, decided_at REAL);
CREATE INDEX IF NOT EXISTS cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS cases_uploader ON cases(uploader_id);
-- Credits only. Nothing here moves real money; payouts need bKash/Nagad + identity checks first.
CREATE TABLE IF NOT EXISTS rewards(
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, case_id TEXT NOT NULL UNIQUE, fine_bdt INT NOT NULL,
  amount_bdt INT NOT NULL, status TEXT NOT NULL DEFAULT 'credited', created_at REAL);
CREATE INDEX IF NOT EXISTS rewards_user ON rewards(user_id);
CREATE INDEX IF NOT EXISTS videos_user ON videos(user_id);
-- Every admin action, for accountability (backend/admin.py).
CREATE TABLE IF NOT EXISTS admin_log(
  id TEXT PRIMARY KEY, admin_id TEXT NOT NULL, action TEXT NOT NULL, target TEXT, detail TEXT, created_at REAL);
CREATE INDEX IF NOT EXISTS admin_log_time ON admin_log(created_at);
-- one-time password-reset links; only the SHA-256 of the token is stored
CREATE TABLE IF NOT EXISTS password_resets(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at REAL,
  expires_at REAL, used_at REAL, created_by TEXT);
CREATE INDEX IF NOT EXISTS password_resets_user ON password_resets(user_id);

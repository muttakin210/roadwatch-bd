-- Production schema, first version (PLAN §8.3). Postgres / Supabase.
create type user_role as enum ('user', 'moderator', 'admin');
create type video_status as enum ('uploaded', 'queued', 'processing', 'done', 'failed');
create type moderation_status as enum ('pending', 'ok', 'rejected', 'taken_down');
create type location_source as enum ('gps', 'user', 'none');

create table users (
  id uuid primary key default gen_random_uuid(),
  email text unique, name text, role user_role not null default 'user',
  created_at timestamptz not null default now()
);

create table videos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid null references users(id),
  storage_key text not null, content_hash text, perceptual_hash text,
  duration_s real, fps real, width int, height int, orientation text, camera_type text,
  lat double precision, lng double precision, place_name text,
  location_source location_source not null default 'none',
  recorded_at timestamptz,
  status video_status not null default 'uploaded',
  moderation_status moderation_status not null default 'pending',
  consent_training bool not null default false,
  created_at timestamptz not null default now(),
  raw_deleted_at timestamptz
);
create index on videos (content_hash);
create index on videos (perceptual_hash);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  video_id uuid not null references videos(id) on delete cascade,
  model_version text, rules_version text, attempt int not null default 1,
  started_at timestamptz, finished_at timestamptz, error text, progress real
);

create table results (
  video_id uuid not null references videos(id) on delete cascade,
  job_id uuid not null references jobs(id),
  annotated_key text, report_key text, congestion_avg real,
  camera_motion_class text, scene_summary jsonb,
  primary key (job_id)
);

create table events (
  id uuid primary key default gen_random_uuid(),
  video_id uuid not null references videos(id) on delete cascade,
  job_id uuid not null references jobs(id),
  type text not null, subtype text, vehicle_class text, track_id int,
  start_s real not null, end_s real not null, raw_score real, confidence real,
  severity text, reason text, details jsonb, snapshot_key text,
  verified bool not null default false
);
create index on events (video_id);
create index on events (type, verified);

create table event_feedback (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references events(id) on delete cascade,
  user_id uuid null references users(id),
  verdict text not null check (verdict in ('correct', 'wrong', 'wrong_type')),
  corrected_type text, note text,
  created_at timestamptz not null default now()
);

create table road_hints (
  video_id uuid primary key references videos(id) on delete cascade,
  arrows jsonb, road_points jsonb, edge_taps jsonb
);

-- Raw video retention: 30 days unless training consent (PLAN §8.6). Run daily:
-- update videos set raw_deleted_at = now()
--  where raw_deleted_at is null and not consent_training and created_at < now() - interval '30 days';

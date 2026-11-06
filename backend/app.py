"""RoadWatch BD — Phase-1 prototype API (PLAN §8.4).

Prototype simplifications (replace in Phase 7, PLAN §8.2): SQLite instead of Supabase/Postgres,
an in-process worker thread instead of Redis + Celery and a sandboxed GPU worker, a plain
multipart upload instead of tus resumable uploads, no Turnstile.

    cd backend && uvicorn app:app --reload
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import accounts
import admin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

DATA = Path(os.environ.get("ROADWATCH_DATA", ROOT / "data" / "platform"))
UPLOADS, RESULTS = DATA / "uploads", DATA / "results"   # uploads are private: never served
for p in (UPLOADS, RESULTS):
    p.mkdir(parents=True, exist_ok=True)
DB = DATA / "roadwatch.sqlite"
MAX_BYTES = 200 * 1024 * 1024
DAILY_LIMIT_PER_IP = int(os.environ.get("ROADWATCH_DAILY_LIMIT", 20))
DETECTOR = os.environ.get("ROADWATCH_DETECTOR", "hf")
ALLOW_NO_FFMPEG = os.environ.get("ROADWATCH_ALLOW_NO_FFMPEG") == "1"   # development only
# Privacy policy / PLAN §8.7: the raw upload is deleted after this many days unless the uploader gave
# training consent. Only the blurred annotated video and the report are kept.
RETENTION_S = int(os.environ.get("ROADWATCH_RAW_RETENTION_DAYS", 30)) * 86400
PARTIAL_MAX_AGE_S = 24 * 3600          # unfinished chunked uploads are dropped after a day
PROGRESS_KEEP_S = 10 * 60              # finished jobs leave the in-memory progress table after this
HOUSEKEEPING_EVERY_S = 3600
FEEDBACK_LIMIT, REPORT_LIMIT = 60, 10  # per visitor address per 15 min
EVENT_TYPES = {"congestion_jam", "bus_midroad_stop", "wrong_way", "u_turn"}

log = logging.getLogger("roadwatch.api")


@asynccontextmanager
async def _lifespan(_app):
    _startup()   # only when actually serving (not when manage.py or a test imports this module)
    yield


app = FastAPI(title="RoadWatch BD (prototype)", lifespan=_lifespan)
pool = ThreadPoolExecutor(max_workers=1)
_progress: dict[str, dict] = {}
_ip_counts: dict[tuple[str, str], int] = {}
_lock = threading.Lock()
_detector = None


class _Conn(sqlite3.Connection):
    """`with db() as c:` commits (or rolls back) and then closes, so connections never pile up."""

    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def db() -> sqlite3.Connection:
    # timeout: the worker thread and requests write at the same time; wait for the lock instead of failing
    c = sqlite3.connect(DB, check_same_thread=False, timeout=30, factory=_Conn)
    c.row_factory = sqlite3.Row
    return c


with db() as c:
    c.execute("PRAGMA journal_mode=WAL")   # readers don't block the writer (persists in the database file)
    c.executescript((Path(__file__).with_name("schema_sqlite.sql")).read_text())
accounts.setup(db)
app.include_router(accounts.router)


@app.middleware("http")
async def only_via_proxy(request: Request, call_next):
    """With ROADWATCH_PROXY_SECRET set (public deployment), refuse anything that didn't come through the
    web app's proxy: the tunnel URL alone gives no access to the API or the bare upload page."""
    if accounts.PROXY_SECRET and not accounts.from_proxy(request):
        return JSONResponse({"detail": "not found"}, status_code=404)
    return await call_next(request)


# --------------------------------------------------------------------------- worker
def _get_detector():
    global _detector
    if _detector is None:
        from roadwatch.detect import make_detector
        _detector = make_detector(DETECTOR)
    return _detector


def _set_progress(video_id: str, step: str, frac: float, **extra) -> None:
    _progress[video_id] = {"step": step, "progress": round(frac, 3), **extra, "at": time.time()}


class _VideoGone(Exception):
    """The video was deleted while it was being analysed."""


def _process(video_id: str, job_id: str) -> None:
    from roadwatch.pipeline import run_video
    with db() as c:
        v = c.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if v is None:   # deleted while it waited in the queue
            c.execute("UPDATE jobs SET finished_at=?, error=? WHERE id=?", (time.time(), "video deleted", job_id))
            _progress.pop(video_id, None)
            return
        c.execute("UPDATE videos SET status='processing' WHERE id=?", (video_id,))
        c.execute("UPDATE jobs SET started_at=? WHERE id=?", (time.time(), job_id))

    def progress(step: str, frac: float):
        _set_progress(video_id, step, frac)

    out = RESULTS / video_id
    try:
        progress("starting", 0)
        raw = UPLOADS / Path(v["storage_key"]).name
        if not raw.exists():
            raise RuntimeError("the original upload was already deleted")
        res = run_video(raw, out, json.loads(v["hints"] or "{}"),
                        detector=_get_detector(), progress=progress, allow_no_ffmpeg=ALLOW_NO_FFMPEG)
        with db() as c:
            # First statement takes the write lock, so an admin delete can't slip in between check and inserts.
            if not c.execute("UPDATE videos SET status='done', duration_s=? WHERE id=?",
                             (res["duration_s"], video_id)).rowcount:
                raise _VideoGone
            c.execute("INSERT INTO results(video_id, job_id, annotated_key, report_key, congestion_avg, "
                      "camera_motion_class, scene_summary) VALUES (?,?,?,?,?,?,?)",
                      (video_id, job_id, f"{video_id}/annotated.mp4", f"{video_id}/events.json",
                       res["congestion"]["avg"], res["camera_motion"], json.dumps(res["summary"])))
            for e in res["events"]:
                c.execute("INSERT INTO events(id, video_id, job_id, type, subtype, vehicle_class, track_id, start_s, "
                          "end_s, raw_score, confidence, severity, reason, details) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (uuid.uuid4().hex, video_id, job_id, e["type"], e.get("subtype"), e.get("vehicle_class"),
                           e.get("track"), e["start"], e["end"], e["raw_score"], e.get("confidence"),
                           e.get("severity"), e["reason"], json.dumps(e.get("details", {}))))
            c.execute("UPDATE jobs SET finished_at=?, model_version=?, rules_version=? WHERE id=?",
                      (time.time(), res["model_version"], res["rules_version"], job_id))
        progress("done", 1)
    except _VideoGone:
        log.info("video %s was deleted during job %s; discarding its results", video_id, job_id)
        if out.parent == RESULTS:
            shutil.rmtree(out, ignore_errors=True)
        _progress.pop(video_id, None)
    except Exception as ex:  # keep the error visible to the user and in the job row
        log.exception("job %s failed", job_id)
        with db() as c:
            # a failed RE-analysis keeps the earlier, still valid results visible
            had = c.execute("SELECT 1 FROM results WHERE video_id=?", (video_id,)).fetchone()
            c.execute("UPDATE videos SET status=? WHERE id=?", ("done" if had else "failed", video_id))
            c.execute("UPDATE jobs SET finished_at=?, error=? WHERE id=?", (time.time(), str(ex)[:500], job_id))
        _set_progress(video_id, "failed", 1, error=str(ex)[:200])


def _enqueue(video_id: str) -> str:
    job_id = uuid.uuid4().hex
    with db() as c:
        attempt = c.execute("SELECT COUNT(*) FROM jobs WHERE video_id=?", (video_id,)).fetchone()[0] + 1
        c.execute("INSERT INTO jobs(id, video_id, attempt) VALUES (?,?,?)", (job_id, video_id, attempt))
        c.execute("UPDATE videos SET status='queued' WHERE id=?", (video_id,))
    _set_progress(video_id, "queued", 0)
    pool.submit(_process, video_id, job_id)
    return job_id


def _raw_exists(storage_key: str) -> bool:
    return (UPLOADS / Path(storage_key).name).exists()


def recover_jobs() -> int:
    """After a restart the in-memory queue is gone: re-queue unfinished videos (or fail them if the upload is gone)."""
    now = time.time()
    with db() as c:
        rows = c.execute("SELECT id, storage_key FROM videos WHERE status IN ('uploaded','queued','processing')").fetchall()
        c.execute("UPDATE jobs SET finished_at=?, error='interrupted by a server restart' WHERE finished_at IS NULL",
                  (now,))
    n = 0
    for r in rows:
        if _raw_exists(r["storage_key"]):
            _enqueue(r["id"])
            n += 1
        else:
            with db() as c:
                had = c.execute("SELECT 1 FROM results WHERE video_id=?", (r["id"],)).fetchone()
                c.execute("UPDATE videos SET status=? WHERE id=?", ("done" if had else "failed", r["id"]))
    return n


def housekeeping(now: float | None = None) -> dict:
    """Retention + cleanup. Runs at startup and then every HOUSEKEEPING_EVERY_S."""
    now = time.time() if now is None else now
    out = {"raw_deleted": 0, "partials_deleted": 0}
    # 1. raw uploads past retention, unless the uploader consented to training use (privacy policy)
    with db() as c:
        rows = c.execute("SELECT id, storage_key FROM videos WHERE raw_deleted_at IS NULL "
                         "AND COALESCE(consent_training, 0) = 0 AND created_at < ? "
                         "AND status NOT IN ('uploaded','queued','processing')", (now - RETENTION_S,)).fetchall()
    for r in rows:
        (UPLOADS / Path(r["storage_key"]).name).unlink(missing_ok=True)
        with db() as c:
            c.execute("UPDATE videos SET raw_deleted_at=? WHERE id=?", (now, r["id"]))
        out["raw_deleted"] += 1
    # 2. abandoned chunked uploads
    for stem in {f.stem for f in PARTIAL.iterdir() if f.suffix in (".json", ".part")}:
        meta, part = PARTIAL / f"{stem}.json", PARTIAL / f"{stem}.part"
        try:
            created = json.loads(meta.read_text())["created"]
        except (OSError, ValueError, KeyError):   # no/broken metadata: judge by the newest file's age
            try:
                created = max(p.stat().st_mtime for p in (meta, part) if p.exists())
            except ValueError:
                continue
        if now - created > PARTIAL_MAX_AGE_S:
            part.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            out["partials_deleted"] += 1
    # 3. in-memory tables
    today = time.strftime("%Y-%m-%d")
    with _lock:
        for k in [k for k in _ip_counts if k[1] != today]:
            del _ip_counts[k]
    for k, p in list(_progress.items()):
        if p.get("step") in ("done", "failed") and now - p.get("at", now) > PROGRESS_KEEP_S:
            _progress.pop(k, None)
    return out


def _housekeeping_loop() -> None:
    while True:
        time.sleep(HOUSEKEEPING_EVERY_S)
        try:
            housekeeping()
        except Exception:
            log.exception("housekeeping failed")


def _startup() -> None:
    housekeeping()
    n = recover_jobs()
    if n:
        log.info("re-queued %d unfinished video(s) after a restart", n)
    threading.Thread(target=_housekeeping_loop, daemon=True, name="housekeeping").start()


admin.setup(db=db, uploads=UPLOADS, results=RESULTS, enqueue=_enqueue, progress=_progress,
            info=lambda: {"detector": DETECTOR, "daily_upload_limit_per_ip": DAILY_LIMIT_PER_IP,
                          "max_upload_mb": MAX_BYTES // (1024 * 1024)})
app.include_router(admin.router)

import news  # noqa: E402

app.include_router(news.router)

import maps  # noqa: E402

maps.setup(db, DATA)
app.include_router(maps.router)
if os.environ.get("ROADWATCH_NEWS", "1") == "1":   # tests and offline development set ROADWATCH_NEWS=0
    news.start()


def _vid_ok(vid: str) -> str:
    if not (len(vid) == 32 and all(ch in "0123456789abcdef" for ch in vid)):
        raise HTTPException(404)
    return vid


def _is_staff(me) -> bool:
    return bool(me and me["role"] in ("reviewer", "police", "admin"))


def _visible(vid: str, request: Request) -> sqlite3.Row:
    """404 for unknown videos, and for hidden ones unless you're the uploader or staff."""
    with db() as c:
        v = c.execute("SELECT user_id, moderation_status FROM videos WHERE id=?", (vid,)).fetchone()
    if not v:
        raise HTTPException(404)
    if v["moderation_status"] == "hidden":
        me = accounts.current_user(request)
        if not (me and (me["id"] == v["user_id"] or _is_staff(me))):
            raise HTTPException(404)
    return v


# --------------------------------------------------------------------------- input checks
def _num(v, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise HTTPException(400, "invalid hints")
    return float(v)


def _points(v, max_n: int) -> list[list[float]]:
    if not isinstance(v, list) or not 1 <= len(v) <= max_n:
        raise HTTPException(400, "invalid hints")
    out = []
    for p in v:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise HTTPException(400, "invalid hints")
        out.append([_num(p[0], -100, 10_000), _num(p[1], -100, 10_000)])
    return out


def clean_hints(h) -> dict:
    """Only known keys with the right types and sane sizes reach the pipeline (unknown keys are dropped)."""
    if not isinstance(h, dict):
        raise HTTPException(400, "hints must be a JSON object")
    out: dict = {}
    for k in ("camera_along_road", "oneway", "near_bus_stop"):
        if h.get(k) is not None:
            if not isinstance(h[k], bool):
                raise HTTPException(400, "invalid hints")
            out[k] = h[k]
    if h.get("arrows"):
        a = h["arrows"]
        if not isinstance(a, list) or len(a) > 20:
            raise HTTPException(400, "at most 20 arrows")
        arrows = []
        for x in a:
            if not isinstance(x, (list, tuple)) or len(x) != 4:
                raise HTTPException(400, "invalid hints")
            arrows.append([_num(v, -100, 10_000) for v in x])
        out["arrows"] = arrows
    if h.get("road_edges"):
        e = h["road_edges"]
        if not isinstance(e, dict) or not {"left", "right"} <= set(e) or set(e) - {"left", "right", "divider"}:
            raise HTTPException(400, "invalid hints")
        out["road_edges"] = {k: _points(v, 50) for k, v in e.items() if v}
    if h.get("trim") is not None:
        t = h["trim"]
        if not isinstance(t, (list, tuple)) or len(t) != 2:
            raise HTTPException(400, "invalid trim")
        s, e = _num(t[0], 0, 86_400), _num(t[1], 0, 86_400)
        if not 0 < e - s <= 301:
            raise HTTPException(400, "invalid trim")
        out["trim"] = [s, e]
    return out


def _coords(lat, lng) -> tuple[float | None, float | None]:
    if lat is None and lng is None:
        return None, None
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        raise HTTPException(400, "lat and lng must be numbers") from None
    if not (math.isfinite(la) and math.isfinite(ln) and -90 <= la <= 90 and -180 <= ln <= 180):
        raise HTTPException(400, "lat/lng out of range")
    return la, ln


# --------------------------------------------------------------------------- API
@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).with_name("static") / "index.html").read_text(encoding="utf-8")


def _rate_limit(request: Request) -> None:
    ip = accounts.client_ip(request)
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if any(k[1] != day for k in _ip_counts):   # a new day: yesterday's counters are useless
            for k in [k for k in _ip_counts if k[1] != day]:
                del _ip_counts[k]
        n = _ip_counts.get((ip, day), 0)
        if n >= DAILY_LIMIT_PER_IP:
            raise HTTPException(429, "daily upload limit reached")
        _ip_counts[(ip, day)] = n + 1


def _register(video_id: str, key: str, hints: dict, camera_type: str, consent: bool,
              lat: float | None, lng: float | None, user_id: str | None = None) -> dict:
    if camera_type not in CAMERA_TYPES:
        raise HTTPException(400, f"camera_type must be one of {sorted(CAMERA_TYPES)}")
    hints = dict(hints)
    hints["camera_type"] = camera_type
    with db() as c:
        c.execute("INSERT INTO videos(id, user_id, storage_key, camera_type, lat, lng, location_source, status, "
                  "moderation_status, consent_training, hints, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (video_id, user_id, key, camera_type, lat, lng, "user" if lat is not None else "none", "uploaded",
                   "pending", int(consent), json.dumps(hints), time.time()))
    _enqueue(video_id)
    return {"id": video_id}


# ---- resumable chunked upload (mobile connections drop; PLAN §8.1) -----------------------
CHUNK_BYTES = 4 * 1024 * 1024
PARTIAL = UPLOADS / "partial"
PARTIAL.mkdir(exist_ok=True)
CAMERA_TYPES = {"footbridge", "roadside", "cctv", "vehicle"}


class UploadInit(BaseModel):
    size: int


def _upload_paths(uid: str) -> tuple[Path, Path]:
    if not (len(uid) == 32 and all(ch in "0123456789abcdef" for ch in uid)):
        raise HTTPException(404)
    return PARTIAL / f"{uid}.part", PARTIAL / f"{uid}.json"


@app.post("/api/uploads")
def create_upload(request: Request, init: UploadInit):
    if not 0 < init.size <= MAX_BYTES:
        raise HTTPException(413, "file larger than 200 MB")
    _rate_limit(request)
    uid = uuid.uuid4().hex
    part, meta = _upload_paths(uid)
    part.write_bytes(b"")
    meta.write_text(json.dumps({"size": init.size, "created": time.time()}))
    return {"id": uid, "chunk_size": CHUNK_BYTES, "offset": 0}


@app.get("/api/uploads/{uid}")
def upload_status(uid: str):
    part, meta = _upload_paths(uid)
    if not meta.exists():
        raise HTTPException(404)
    return {"offset": part.stat().st_size, "size": json.loads(meta.read_text())["size"]}


@app.put("/api/uploads/{uid}")
async def upload_chunk(uid: str, request: Request, offset: int):
    part, meta = _upload_paths(uid)
    if not meta.exists():
        raise HTTPException(404)
    # Read the body FIRST. Everything after this line runs without an `await`, so on the event loop the
    # offset check and the append are atomic: a retry that overlaps a slow request can't append twice.
    body = await request.body()
    if not meta.exists():
        raise HTTPException(404)
    size = json.loads(meta.read_text())["size"]
    cur = part.stat().st_size
    if offset != cur:  # client resumes from where the server actually is
        raise HTTPException(409, detail={"offset": cur})
    if len(body) > CHUNK_BYTES or cur + len(body) > size:
        raise HTTPException(413, "chunk too large")
    with open(part, "ab") as f:
        f.write(body)
    return {"offset": cur + len(body), "size": size}


class VideoCreate(BaseModel):
    upload_id: str
    hints: dict = {}
    camera_type: str = "footbridge"
    consent_training: bool = False
    lat: float | None = None
    lng: float | None = None


@app.post("/api/videos")
async def create_video(request: Request):
    """JSON {upload_id, ...} after a chunked upload, or legacy multipart (bare prototype page)."""
    video_id = uuid.uuid4().hex
    key = f"{video_id}.bin"   # never trust the client's file name or extension
    me = accounts.current_user(request)   # anonymous uploads stay allowed; logged-in ones are owned
    uid = me["id"] if me else None
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            v = VideoCreate(**await request.json())
        except Exception:
            raise HTTPException(400, "invalid request")
        if v.camera_type not in CAMERA_TYPES:  # validate before consuming the upload
            raise HTTPException(400, f"camera_type must be one of {sorted(CAMERA_TYPES)}")
        hints = clean_hints(v.hints)
        lat, lng = _coords(v.lat, v.lng)
        part, meta = _upload_paths(v.upload_id)
        if not meta.exists():
            raise HTTPException(404, "unknown upload")
        if part.stat().st_size != json.loads(meta.read_text())["size"]:
            raise HTTPException(409, "upload incomplete")
        try:
            part.replace(UPLOADS / key)
        except FileNotFoundError:
            raise HTTPException(404, "unknown upload") from None
        meta.unlink(missing_ok=True)
        return _register(video_id, key, hints, v.camera_type, v.consent_training, lat, lng, uid)

    form = await request.form()
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise HTTPException(400, "file is required")
    try:
        h = json.loads(form.get("hints") or "{}")
    except ValueError:
        raise HTTPException(400, "hints must be a JSON object") from None
    hints = clean_hints(h)
    camera_type = form.get("camera_type") or "footbridge"
    if camera_type not in CAMERA_TYPES:   # check everything before writing the file
        raise HTTPException(400, f"camera_type must be one of {sorted(CAMERA_TYPES)}")
    lat, lng = _coords(form.get("lat") or None, form.get("lng") or None)
    _rate_limit(request)
    size = 0
    with open(UPLOADS / key, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_BYTES:
                f.close(); (UPLOADS / key).unlink(missing_ok=True)
                raise HTTPException(413, "file larger than 200 MB")
            f.write(chunk)
    return _register(video_id, key, hints, camera_type,
                     str(form.get("consent_training")).lower() == "true", lat, lng, uid)


@app.get("/api/videos/{vid}/events.json")
def events_json(vid: str, request: Request):
    """Downloadable report (no video, no plates)."""
    _vid_ok(vid)
    _visible(vid, request)
    p = RESULTS / vid / "events.json"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/json", filename=f"roadwatch_{vid[:8]}.json")


@app.get("/api/videos/{vid}")
def get_video(vid: str, request: Request):
    _visible(vid, request)
    me = accounts.current_user(request)
    with db() as c:
        v = c.execute("SELECT id, user_id, status, duration_s, camera_type, created_at FROM videos WHERE id=?",
                      (vid,)).fetchone()
        if not v:
            raise HTTPException(404)
        r = c.execute("SELECT congestion_avg, camera_motion_class, scene_summary FROM results WHERE video_id=? "
                      "ORDER BY rowid DESC LIMIT 1", (vid,)).fetchone()
        uploader = accounts.uploader_json(c, v["user_id"])
    out = {k: v[k] for k in ("id", "status", "duration_s", "camera_type", "created_at")} | {
        "progress": _public_progress(vid), "uploader": uploader,
        "is_owner": bool(me and v["user_id"] and me["id"] == v["user_id"])}
    if r:
        out |= {"congestion_avg": r["congestion_avg"], "camera_motion": r["camera_motion_class"],
                "summary": json.loads(r["scene_summary"] or "{}"), "notes": _notes(vid)}
    return out


def _public_progress(vid: str) -> dict | None:
    p = _progress.get(vid)
    return {k: v for k, v in p.items() if k != "at"} if p else None


def _notes(vid: str) -> list[dict]:
    """Road-level notes from the saved report: [{k, en, ...args}]. Reports written before notes were
    translatable only have English strings; those come back as {en} and the web app shows them as-is."""
    p = RESULTS / vid / "events.json"
    if not (len(vid) == 32 and vid.isalnum()) or not p.exists():
        return []
    try:
        rep = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("unreadable report for %s", vid)
        return []
    return rep.get("note_parts") or [{"en": n} for n in rep.get("notes", [])]


@app.get("/api/videos/{vid}/events")
def get_events(vid: str, request: Request, include_uncertain: int = 0):
    _visible(vid, request)
    me = accounts.current_user(request)
    with db() as c:
        job = c.execute("SELECT job_id FROM results WHERE video_id=? ORDER BY rowid DESC LIMIT 1", (vid,)).fetchone()
        if not job:
            return {"events": []}
        owner = c.execute("SELECT user_id FROM videos WHERE id=?", (vid,)).fetchone()
        is_owner = bool(me and owner and owner["user_id"] == me["id"])
        # The latest analysis, plus (for the uploader and staff) events from earlier analyses that were already
        # submitted as cases, so a re-analysis never makes a submitted case vanish from the video page.
        older = is_owner or _is_staff(me)
        rows = c.execute("SELECT e.id, e.type, e.subtype, e.vehicle_class, e.track_id, e.start_s, e.end_s, e.confidence, "
                         "e.severity, e.reason, e.details, e.verified, e.job_id, k.status AS case_status FROM events e "
                         "LEFT JOIN cases k ON k.event_id = e.id "
                         "WHERE e.job_id=? OR (? AND e.video_id=? AND k.id IS NOT NULL) ORDER BY e.start_s",
                         (job["job_id"], int(older), vid)).fetchall()
    evs = []
    for r in rows:
        d = dict(r) | {"details": json.loads(r["details"] or "{}"), "verified": bool(r["verified"]),
                       "reportable": r["type"] in accounts.CASE_TYPES}
        stale = d.pop("job_id") != job["job_id"]
        if stale:
            d["earlier_analysis"] = True
        if not is_owner:   # a case's progress is the uploader's business
            d.pop("case_status")
        if stale or include_uncertain or d["details"].get("shown", True):
            evs.append(d)
    return {"events": evs, "label": "possible incident (AI-detected, may be wrong)"}


@app.get("/api/videos/{vid}/stream")
async def stream(vid: str, request: Request):
    _vid_ok(vid)
    _visible(vid, request)   # hidden videos: not even their progress

    async def gen():
        last = None
        for _ in range(3600):
            if await request.is_disconnected():
                return
            p = _public_progress(vid)
            if p is None:  # e.g. after a server restart: fall back to the stored status
                with db() as c:
                    row = c.execute("SELECT status FROM videos WHERE id=?", (vid,)).fetchone()
                if not row:
                    yield 'data: {"step": "failed", "progress": 1, "error": "unknown video"}\n\n'
                    return
                if row["status"] in ("done", "failed"):
                    p = {"step": row["status"], "progress": 1}
            if p != last:
                yield f"data: {json.dumps(p)}\n\n"
                last = dict(p) if p else None
            if p and p["step"] in ("done", "failed"):
                return
            await asyncio.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/videos/{vid}/annotated")
def annotated(vid: str, request: Request):
    """Only the blurred, annotated video is ever served (PLAN §5.7, §8.7)."""
    _vid_ok(vid)
    _visible(vid, request)
    p = RESULTS / vid / "annotated.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


@app.post("/api/videos/{vid}/reanalyse")
def reanalyse(vid: str, request: Request):
    me = accounts.current_user(request)
    with db() as c:
        v = c.execute("SELECT user_id, storage_key, status FROM videos WHERE id=?", (vid,)).fetchone()
    if not v:
        raise HTTPException(404)
    # Owner, reviewer or admin only. Anonymous uploads have no owner, so only staff may re-run them: one
    # worker serves everybody, and re-analysis is a full ML run.
    if not (me and ((v["user_id"] and me["id"] == v["user_id"]) or me["role"] in ("reviewer", "admin"))):
        raise HTTPException(403, "only the uploader can re-analyse this video")
    if v["status"] in ("uploaded", "queued", "processing"):
        raise HTTPException(409, "this video is already being analysed")
    if not _raw_exists(v["storage_key"]):
        raise HTTPException(409, "the original upload was already deleted")
    return {"job_id": _enqueue(vid)}   # old results are kept; a new result row is added


class Feedback(BaseModel):
    verdict: str            # correct | wrong | wrong_type
    corrected_type: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=1000)


@app.post("/api/events/{eid}/feedback", dependencies=[Depends(accounts.require_json)])
def feedback(eid: str, fb: Feedback, request: Request):
    if fb.verdict not in ("correct", "wrong", "wrong_type"):
        raise HTTPException(400, "verdict must be correct | wrong | wrong_type")
    if fb.corrected_type is not None and fb.corrected_type not in EVENT_TYPES:
        raise HTTPException(400, f"corrected_type must be one of {sorted(EVENT_TYPES)}")
    accounts.throttle(f"feedback:{accounts.client_ip(request)}", FEEDBACK_LIMIT)
    with db() as c:
        e = c.execute("SELECT video_id FROM events WHERE id=?", (eid,)).fetchone()
    if not e:
        raise HTTPException(404)
    _visible(e["video_id"], request)
    me = accounts.current_user(request)
    with db() as c:
        c.execute("INSERT INTO event_feedback(id, event_id, user_id, verdict, corrected_type, note, created_at) "
                  "VALUES (?,?,?,?,?,?,?)", (uuid.uuid4().hex, eid, me["id"] if me else None, fb.verdict,
                                            fb.corrected_type, (fb.note or "") or None, time.time()))
    return {"ok": True}


class Report(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@app.post("/api/videos/{vid}/report", dependencies=[Depends(accounts.require_json)])
def report(vid: str, r: Report, request: Request):
    accounts.throttle(f"report:{accounts.client_ip(request)}", REPORT_LIMIT)
    with db() as c:
        if not c.execute("SELECT 1 FROM videos WHERE id=?", (vid,)).fetchone():
            raise HTTPException(404)
        # flag for the admin panel; never un-hide a video an admin has hidden
        c.execute("UPDATE videos SET moderation_status='pending' WHERE id=? AND moderation_status != 'hidden'", (vid,))
        c.execute("INSERT INTO reports(id, video_id, reason, created_at) VALUES (?,?,?,?)",
                  (uuid.uuid4().hex, vid, r.reason.strip(), time.time()))
    return {"ok": True}

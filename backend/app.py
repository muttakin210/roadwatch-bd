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
import os
import sqlite3
import sys
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

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

log = logging.getLogger("roadwatch.api")
app = FastAPI(title="RoadWatch BD (prototype)")
pool = ThreadPoolExecutor(max_workers=1)
_progress: dict[str, dict] = {}
_ip_counts: dict[tuple[str, str], int] = defaultdict(int)
_lock = threading.Lock()
_detector = None


def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


with db() as c:
    c.executescript((Path(__file__).with_name("schema_sqlite.sql")).read_text())


# --------------------------------------------------------------------------- worker
def _get_detector():
    global _detector
    if _detector is None:
        from roadwatch.detect import make_detector
        _detector = make_detector(DETECTOR)
    return _detector


def _process(video_id: str, job_id: str) -> None:
    from roadwatch.pipeline import run_video
    with db() as c:
        v = c.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        c.execute("UPDATE videos SET status='processing' WHERE id=?", (video_id,))
        c.execute("UPDATE jobs SET started_at=? WHERE id=?", (time.time(), job_id))

    def progress(step: str, frac: float):
        _progress[video_id] = {"step": step, "progress": round(frac, 3)}

    try:
        progress("starting", 0)
        res = run_video(UPLOADS / v["storage_key"], RESULTS / video_id, json.loads(v["hints"] or "{}"),
                        detector=_get_detector(), progress=progress, allow_no_ffmpeg=ALLOW_NO_FFMPEG)
        with db() as c:
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
            c.execute("UPDATE videos SET status='done', duration_s=? WHERE id=?", (res["duration_s"], video_id))
            c.execute("UPDATE jobs SET finished_at=?, model_version=?, rules_version=? WHERE id=?",
                      (time.time(), res["model_version"], res["rules_version"], job_id))
        progress("done", 1)
    except Exception as ex:  # keep the error visible to the user and in the job row
        log.exception("job %s failed", job_id)
        with db() as c:
            c.execute("UPDATE videos SET status='failed' WHERE id=?", (video_id,))
            c.execute("UPDATE jobs SET finished_at=?, error=? WHERE id=?", (time.time(), str(ex)[:500], job_id))
        _progress[video_id] = {"step": "failed", "progress": 1, "error": str(ex)[:200]}


def _enqueue(video_id: str) -> str:
    job_id = uuid.uuid4().hex
    with db() as c:
        attempt = c.execute("SELECT COUNT(*) FROM jobs WHERE video_id=?", (video_id,)).fetchone()[0] + 1
        c.execute("INSERT INTO jobs(id, video_id, attempt) VALUES (?,?,?)", (job_id, video_id, attempt))
        c.execute("UPDATE videos SET status='queued' WHERE id=?", (video_id,))
    _progress[video_id] = {"step": "queued", "progress": 0}
    pool.submit(_process, video_id, job_id)
    return job_id


# --------------------------------------------------------------------------- API
@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).with_name("static") / "index.html").read_text(encoding="utf-8")


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    day = time.strftime("%Y-%m-%d")
    with _lock:
        if _ip_counts[(ip, day)] >= DAILY_LIMIT_PER_IP:
            raise HTTPException(429, "daily upload limit reached")
        _ip_counts[(ip, day)] += 1


def _register(video_id: str, key: str, hints: dict, camera_type: str, consent: bool,
              lat: float | None, lng: float | None) -> dict:
    if camera_type not in CAMERA_TYPES:
        raise HTTPException(400, f"camera_type must be one of {sorted(CAMERA_TYPES)}")
    hints = dict(hints)
    hints["camera_type"] = camera_type
    with db() as c:
        c.execute("INSERT INTO videos(id, storage_key, camera_type, lat, lng, location_source, status, "
                  "moderation_status, consent_training, hints, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (video_id, key, camera_type, lat, lng, "user" if lat is not None else "none", "uploaded",
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
    size = json.loads(meta.read_text())["size"]
    cur = part.stat().st_size
    if offset != cur:  # client resumes from where the server actually is
        raise HTTPException(409, detail={"offset": cur})
    body = await request.body()
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
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            v = VideoCreate(**await request.json())
        except Exception:
            raise HTTPException(400, "invalid request")
        if v.camera_type not in CAMERA_TYPES:  # validate before consuming the upload
            raise HTTPException(400, f"camera_type must be one of {sorted(CAMERA_TYPES)}")
        part, meta = _upload_paths(v.upload_id)
        if not meta.exists():
            raise HTTPException(404, "unknown upload")
        if part.stat().st_size != json.loads(meta.read_text())["size"]:
            raise HTTPException(409, "upload incomplete")
        part.replace(UPLOADS / key)
        meta.unlink()
        return _register(video_id, key, v.hints, v.camera_type, v.consent_training, v.lat, v.lng)

    form = await request.form()
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise HTTPException(400, "file is required")
    _rate_limit(request)
    try:
        h = json.loads(form.get("hints") or "{}")
        assert isinstance(h, dict)
    except Exception:
        raise HTTPException(400, "hints must be a JSON object")
    size = 0
    with open(UPLOADS / key, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_BYTES:
                f.close(); (UPLOADS / key).unlink(missing_ok=True)
                raise HTTPException(413, "file larger than 200 MB")
            f.write(chunk)
    lat, lng = form.get("lat"), form.get("lng")
    return _register(video_id, key, h, form.get("camera_type") or "footbridge",
                     str(form.get("consent_training")).lower() == "true",
                     float(lat) if lat else None, float(lng) if lng else None)


@app.get("/api/videos/{vid}/events.json")
def events_json(vid: str):
    """Downloadable report (no video, no plates)."""
    if not (len(vid) == 32 and vid.isalnum()):
        raise HTTPException(404)
    p = RESULTS / vid / "events.json"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/json", filename=f"roadwatch_{vid[:8]}.json")


@app.get("/api/videos/{vid}")
def get_video(vid: str):
    with db() as c:
        v = c.execute("SELECT id, status, duration_s, camera_type, created_at FROM videos WHERE id=?", (vid,)).fetchone()
        if not v:
            raise HTTPException(404)
        r = c.execute("SELECT congestion_avg, camera_motion_class, scene_summary FROM results WHERE video_id=? "
                      "ORDER BY rowid DESC LIMIT 1", (vid,)).fetchone()
    out = dict(v) | {"progress": _progress.get(vid)}
    if r:
        out |= {"congestion_avg": r["congestion_avg"], "camera_motion": r["camera_motion_class"],
                "summary": json.loads(r["scene_summary"] or "{}"), "notes": _notes(vid)}
    return out


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
def get_events(vid: str, include_uncertain: int = 0):
    with db() as c:
        job = c.execute("SELECT job_id FROM results WHERE video_id=? ORDER BY rowid DESC LIMIT 1", (vid,)).fetchone()
        if not job:
            return {"events": []}
        rows = c.execute("SELECT id, type, subtype, vehicle_class, track_id, start_s, end_s, confidence, severity, "
                         "reason, details FROM events WHERE job_id=? ORDER BY start_s", (job["job_id"],)).fetchall()
    evs = []
    for r in rows:
        d = dict(r) | {"details": json.loads(r["details"] or "{}")}
        if include_uncertain or d["details"].get("shown", True):
            evs.append(d)
    return {"events": evs, "label": "possible incident (AI-detected, may be wrong)"}


@app.get("/api/videos/{vid}/stream")
async def stream(vid: str):
    async def gen():
        last = None
        for _ in range(3600):
            p = _progress.get(vid)
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
def annotated(vid: str):
    """Only the blurred, annotated video is ever served (PLAN §5.7, §8.7)."""
    if not (len(vid) == 32 and vid.isalnum()):
        raise HTTPException(404)
    p = RESULTS / vid / "annotated.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


@app.post("/api/videos/{vid}/reanalyse")
def reanalyse(vid: str):
    with db() as c:
        if not c.execute("SELECT 1 FROM videos WHERE id=?", (vid,)).fetchone():
            raise HTTPException(404)
    return {"job_id": _enqueue(vid)}   # old results are kept; a new result row is added


class Feedback(BaseModel):
    verdict: str            # correct | wrong | wrong_type
    corrected_type: str | None = None
    note: str | None = None


@app.post("/api/events/{eid}/feedback")
def feedback(eid: str, fb: Feedback):
    if fb.verdict not in ("correct", "wrong", "wrong_type"):
        raise HTTPException(400, "verdict must be correct | wrong | wrong_type")
    with db() as c:
        if not c.execute("SELECT 1 FROM events WHERE id=?", (eid,)).fetchone():
            raise HTTPException(404)
        c.execute("INSERT INTO event_feedback(id, event_id, verdict, corrected_type, note, created_at) "
                  "VALUES (?,?,?,?,?,?)", (uuid.uuid4().hex, eid, fb.verdict, fb.corrected_type,
                                          (fb.note or "")[:1000], time.time()))
    return {"ok": True}


class Report(BaseModel):
    reason: str


@app.post("/api/videos/{vid}/report")
def report(vid: str, r: Report):
    with db() as c:
        c.execute("UPDATE videos SET moderation_status='pending' WHERE id=?", (vid,))
        c.execute("INSERT INTO reports(id, video_id, reason, created_at) VALUES (?,?,?,?)",
                  (uuid.uuid4().hex, vid, r.reason[:1000], time.time()))
    return {"ok": True}

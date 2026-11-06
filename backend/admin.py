"""Admin panel API: overview, users, videos, viewer reports, cases, reward ledger, audit log, system.

Every route requires the admin role (checked server-side from the session), and every change is written
to admin_log with who did it. Destructive actions (delete video, void reward) need an explicit
confirmation field and a reason.
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import accounts
from accounts import audit, require_json, require_role

router = APIRouter(prefix="/api/admin")
ADMIN = Depends(require_role("admin"))
_cfg: dict = {}


def setup(*, db: Callable[[], sqlite3.Connection], uploads: Path, results: Path,
          enqueue: Callable[[str], str], progress: dict, info: Callable[[], dict]) -> None:
    _cfg.update(db=db, uploads=uploads, results=results, enqueue=enqueue, progress=progress, info=info)


def db() -> sqlite3.Connection:
    return _cfg["db"]()


def _vid_ok(vid: str) -> str:
    if not (len(vid) == 32 and all(ch in "0123456789abcdef" for ch in vid)):
        raise HTTPException(404)
    return vid


def _count(c, sql: str, *args) -> dict:
    return {r[0] or "none": r[1] for r in c.execute(sql, args)}


# --------------------------------------------------------------------------- overview
@router.get("/stats")
def stats(_=ADMIN):
    with db() as c:
        return {
            "users": _count(c, "SELECT role, COUNT(*) FROM users GROUP BY role"),
            "disabled_users": c.execute("SELECT COUNT(*) FROM users WHERE disabled=1").fetchone()[0],
            "videos": _count(c, "SELECT status, COUNT(*) FROM videos GROUP BY status"),
            "hidden_videos": c.execute("SELECT COUNT(*) FROM videos WHERE moderation_status='hidden'").fetchone()[0],
            "open_reports": c.execute("SELECT COUNT(*) FROM reports WHERE resolved_at IS NULL").fetchone()[0],
            "cases": _count(c, "SELECT status, COUNT(*) FROM cases GROUP BY status"),
            "rewards_credited_bdt": c.execute(
                "SELECT COALESCE(SUM(amount_bdt), 0) FROM rewards WHERE status='credited'").fetchone()[0],
            "events": _count(c, "SELECT type, COUNT(*) FROM events GROUP BY type"),
        }


@router.get("/system")
def system(_=ADMIN):
    def du(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
    with db() as c:
        queued = c.execute("SELECT COUNT(*) FROM videos WHERE status IN ('queued','processing','uploaded')").fetchone()[0]
        failed = [dict(r) for r in c.execute(
            "SELECT video_id, error, finished_at FROM jobs WHERE error IS NOT NULL ORDER BY finished_at DESC LIMIT 20")]
        last = c.execute("SELECT model_version, rules_version FROM jobs WHERE model_version IS NOT NULL "
                         "ORDER BY finished_at DESC LIMIT 1").fetchone()
    return _cfg["info"]() | {
        "queue": queued, "failed_jobs": failed,
        "model_version": last["model_version"] if last else None, "rules_version": last["rules_version"] if last else None,
        "disk_bytes": {"uploads": du(_cfg["uploads"]), "results": du(_cfg["results"])},
        "in_progress": {k: v for k, v in _cfg["progress"].items() if v.get("step") not in ("done", "failed")},
    }


# --------------------------------------------------------------------------- users
@router.get("/users")
def users(q: str = "", role: str = "", _=ADMIN):
    if role and role not in accounts.ROLES:
        raise HTTPException(400, "unknown role")
    like = f"%{q.strip().lower()}%"
    with db() as c:
        rows = c.execute(
            "SELECT u.id, u.email, u.display_name, u.phone, u.role, u.disabled, u.created_at, "
            "(SELECT COUNT(*) FROM videos WHERE user_id=u.id) AS uploads, "
            "(SELECT COUNT(*) FROM cases WHERE uploader_id=u.id) AS cases, "
            "(SELECT COALESCE(SUM(amount_bdt),0) FROM rewards WHERE user_id=u.id AND status='credited') AS credited_bdt "
            "FROM users u WHERE (lower(u.email) LIKE ? OR lower(u.display_name) LIKE ?) AND (?='' OR u.role=?) "
            "ORDER BY u.created_at DESC LIMIT 200", (like, like, role, role)).fetchall()
    return {"users": [dict(r) | {"disabled": bool(r["disabled"])} for r in rows]}


class Disable(BaseModel):
    disabled: bool
    reason: str | None = Field(default=None, max_length=500)


@router.post("/users/{uid}/disable", dependencies=[Depends(require_json)])
def disable_user(uid: str, body: Disable, me=ADMIN):
    if uid == me["id"]:
        raise HTTPException(400, "you can't disable your own account")
    with db() as c:
        n = c.execute("UPDATE users SET disabled=? WHERE id=?", (int(body.disabled), uid)).rowcount
        if not n:
            raise HTTPException(404)
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))   # takes effect immediately
    audit(me["id"], "disable_user" if body.disabled else "enable_user", uid, body.reason)
    return {"id": uid, "disabled": body.disabled}


@router.post("/users/{uid}/reset-link", dependencies=[Depends(require_json)])
def reset_link(uid: str, me=ADMIN):
    """For a user who forgot their password while email isn't set up: a one-time link the admin passes on.
    The admin never sees or sets the password itself."""
    with accounts.db() as c:
        if not c.execute("SELECT 1 FROM users WHERE id=? AND disabled=0", (uid,)).fetchone():
            raise HTTPException(404, "no such active user")
        token = accounts.create_reset(c, uid, accounts.ADMIN_RESET_S, created_by=me["id"])
    audit(me["id"], "reset_link", uid)
    return {"path": accounts.reset_path(token), "expires_in_s": accounts.ADMIN_RESET_S}


# --------------------------------------------------------------------------- videos
@router.get("/videos")
def videos(status: str = "", moderation: str = "", q: str = "", _=ADMIN):
    like = f"%{q.strip().lower()}%"
    with db() as c:
        rows = c.execute(
            "SELECT v.id, v.status, v.moderation_status, v.camera_type, v.created_at, v.duration_s, v.lat, v.lng, "
            "v.consent_training, u.email AS uploader_email, u.display_name AS uploader_name, "
            "(SELECT COUNT(*) FROM events WHERE video_id=v.id) AS events, "
            "(SELECT COUNT(*) FROM reports WHERE video_id=v.id AND resolved_at IS NULL) AS open_reports, "
            "(SELECT error FROM jobs WHERE video_id=v.id ORDER BY rowid DESC LIMIT 1) AS last_error "
            "FROM videos v LEFT JOIN users u ON u.id = v.user_id "
            "WHERE (?='' OR v.status=?) AND (?='' OR v.moderation_status=?) "
            "AND (?='%%' OR lower(COALESCE(u.email,'')) LIKE ? OR v.id LIKE ?) "
            "ORDER BY v.created_at DESC LIMIT 200",
            (status, status, moderation, moderation, like, like, like)).fetchall()
    return {"videos": [dict(r) for r in rows]}


class Moderation(BaseModel):
    status: Literal["ok", "hidden"]
    reason: str | None = Field(default=None, max_length=500)


@router.post("/videos/{vid}/moderation", dependencies=[Depends(require_json)])
def moderate(vid: str, body: Moderation, me=ADMIN):
    _vid_ok(vid)
    with db() as c:
        if not c.execute("UPDATE videos SET moderation_status=? WHERE id=?", (body.status, vid)).rowcount:
            raise HTTPException(404)
    audit(me["id"], "hide_video" if body.status == "hidden" else "unhide_video", vid, body.reason)
    return {"id": vid, "moderation_status": body.status}


@router.post("/videos/{vid}/reanalyse", dependencies=[Depends(require_json)])
def reanalyse(vid: str, me=ADMIN):
    _vid_ok(vid)
    with db() as c:
        v = c.execute("SELECT storage_key, status FROM videos WHERE id=?", (vid,)).fetchone()
    if not v:
        raise HTTPException(404)
    if v["status"] in ("uploaded", "queued", "processing"):
        raise HTTPException(409, "this video is already being analysed")
    if not (_cfg["uploads"] / Path(v["storage_key"]).name).exists():
        raise HTTPException(409, "the original upload was already deleted")
    job = _cfg["enqueue"](vid)
    audit(me["id"], "reanalyse_video", vid)
    return {"job_id": job}


class Delete(BaseModel):
    confirm: Literal[True]
    reason: str = Field(min_length=3, max_length=500)


@router.post("/videos/{vid}/delete", dependencies=[Depends(require_json)])
def delete_video(vid: str, body: Delete, me=ADMIN):
    _vid_ok(vid)
    with db() as c:
        v = c.execute("SELECT storage_key FROM videos WHERE id=?", (vid,)).fetchone()
        if not v:
            raise HTTPException(404)
        if c.execute("SELECT 1 FROM cases WHERE video_id=? AND status='fined'", (vid,)).fetchone():
            raise HTTPException(409, "a fine was issued from this video: hide it instead, the ledger needs it")
        eids = [r[0] for r in c.execute("SELECT id FROM events WHERE video_id=?", (vid,))]
        c.executemany("DELETE FROM event_feedback WHERE event_id=?", [(e,) for e in eids])
        for table in ("cases", "events", "results", "jobs", "reports"):
            c.execute(f"DELETE FROM {table} WHERE video_id=?", (vid,))
        c.execute("DELETE FROM videos WHERE id=?", (vid,))
    # files: the id was validated as 32 hex chars above, and storage_key is server-generated
    (_cfg["uploads"] / Path(v["storage_key"]).name).unlink(missing_ok=True)
    res = _cfg["results"] / vid
    if res.is_dir() and res.parent == _cfg["results"]:
        shutil.rmtree(res)
    _cfg["progress"].pop(vid, None)
    audit(me["id"], "delete_video", vid, body.reason)
    return {"id": vid, "deleted": True}


# --------------------------------------------------------------------------- viewer reports
@router.get("/reports")
def reports(include_resolved: int = 0, _=ADMIN):
    with db() as c:
        rows = c.execute("SELECT r.id, r.video_id, r.reason, r.created_at, r.resolved_at, v.moderation_status "
                         "FROM reports r LEFT JOIN videos v ON v.id = r.video_id "
                         "WHERE ? OR r.resolved_at IS NULL ORDER BY r.created_at DESC LIMIT 200",
                         (include_resolved,)).fetchall()
    return {"reports": [dict(r) for r in rows]}


@router.post("/reports/{rid}/resolve", dependencies=[Depends(require_json)])
def resolve_report(rid: str, me=ADMIN):
    with db() as c:
        if not c.execute("UPDATE reports SET resolved_at=?, resolved_by=? WHERE id=? AND resolved_at IS NULL",
                         (time.time(), me["id"], rid)).rowcount:
            raise HTTPException(404)
    audit(me["id"], "resolve_report", rid)
    return {"id": rid, "resolved": True}


# --------------------------------------------------------------------------- cases and rewards
@router.get("/cases")
def cases(status: str = "", _=ADMIN):
    with db() as c:
        rows = c.execute("SELECT * FROM cases WHERE (?='' OR status=?) ORDER BY created_at DESC LIMIT 300",
                         (status, status)).fetchall()
        return {"cases": [accounts._case_json(c, r, staff=True) for r in rows]}


@router.get("/rewards")
def rewards(_=ADMIN):
    with db() as c:
        rows = c.execute("SELECT r.*, u.email, u.display_name FROM rewards r LEFT JOIN users u ON u.id = r.user_id "
                         "ORDER BY r.created_at DESC LIMIT 300").fetchall()
    return {"rewards": [dict(r) for r in rows]}


class Void(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/rewards/{rid}/void", dependencies=[Depends(require_json)])
def void_reward(rid: str, body: Void, me=ADMIN):
    with db() as c:
        if not c.execute("UPDATE rewards SET status='void', void_reason=? WHERE id=? AND status='credited'",
                         (body.reason.strip(), rid)).rowcount:
            raise HTTPException(404, "no such credited reward")
    audit(me["id"], "void_reward", rid, body.reason)
    return {"id": rid, "status": "void"}


# --------------------------------------------------------------------------- audit log
@router.get("/log")
def log(_=ADMIN):
    with db() as c:
        rows = c.execute("SELECT l.*, u.email AS admin_email FROM admin_log l LEFT JOIN users u ON u.id = l.admin_id "
                         "ORDER BY l.created_at DESC LIMIT 300").fetchall()
    return {"log": [dict(r) for r in rows]}

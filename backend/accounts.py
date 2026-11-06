"""Accounts, privacy settings and the verified-report workflow.

    AI flags an event -> the uploader submits it as a case -> a reviewer watches the (blurred) video and
    confirms or rejects it -> police record whether a fine was issued -> if fined, 20% of the fine is
    credited to the uploader's reward ledger.

Nothing here fines anyone or moves money. The ledger only records credits; real payouts need a payment
provider (bKash/Nagad), identity checks and an agreement with DMP/BRTA first.

Security notes (see .agentdeck/skills/auth-review.md):
- passwords: scrypt (stdlib), per-user salt, constant-time compare; unknown emails still pay the hash cost
- sessions: 256-bit random token in an HttpOnly, SameSite=Lax cookie; only its SHA-256 is stored;
  rotated on login, all of a user's sessions are dropped on role change; logout deletes server-side
- role and identity always come from the session, never from the request
- state-changing routes require a JSON body (a cross-site HTML form cannot send one) on top of SameSite
- contact details are only shown to reviewers/police, and only if the user opted in
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import fine_rules

router = APIRouter()
_db: Callable[[], sqlite3.Connection] | None = None

COOKIE = "rw_session"
SESSION_S = 30 * 24 * 3600
SECURE_COOKIE = os.environ.get("ROADWATCH_SECURE_COOKIE") == "1"   # always Secure (behind HTTPS only)
# Shared secret with the web app's proxy (web/proxy.ts). When set, every /api request must carry it, and only
# then are the proxy's client-IP / protocol headers trusted. Without it the backend must not be exposed publicly.
PROXY_SECRET = os.environ.get("ROADWATCH_PROXY_SECRET", "")
ROLES = ("user", "reviewer", "police", "admin")
REWARD_SHARE = 0.20
CASE_TYPES = {"wrong_way", "bus_midroad_stop", "u_turn"}            # congestion is not an offence
MAX_FINE_BDT = 100_000
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9 \-]{7,20}$")

_attempts: dict[str, list[float]] = defaultdict(list)
_att_lock = threading.Lock()
# attempts per IP (and per email) per 15 min; raise only for automated test runs
LOGIN_LIMIT, LOGIN_WINDOW_S = int(os.environ.get("ROADWATCH_AUTH_LIMIT", 10)), 15 * 60
EMAIL_FAIL_LIMIT = 5 * LOGIN_LIMIT   # failed logins for one account from all addresses together


def setup(db: Callable[[], sqlite3.Connection]) -> None:
    global _db
    _db = db
    with _att_lock:
        _attempts.clear()
    with db() as c:   # columns added after the first release: migrate existing databases in place
        for table, col, decl in (("users", "disabled", "INT NOT NULL DEFAULT 0"),
                                 ("rewards", "void_reason", "TEXT"),
                                 ("reports", "resolved_at", "REAL"),
                                 ("reports", "resolved_by", "TEXT")):
            if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def db() -> sqlite3.Connection:
    assert _db is not None, "accounts.setup() not called"
    return _db()


# --------------------------------------------------------------------------- passwords
_N, _R, _P = 2 ** 14, 8, 1


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        assert algo == "scrypt"
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    except Exception:
        return False
    return hmac.compare_digest(got.hex(), h)


_DUMMY_HASH = hash_password(secrets.token_hex(8))


# --------------------------------------------------------------------------- sessions
def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def from_proxy(request: Request) -> bool:
    """True if the request came through our web proxy (it knows the shared secret)."""
    got = request.headers.get("x-roadwatch-secret", "")
    return bool(PROXY_SECRET) and hmac.compare_digest(got.encode(), PROXY_SECRET.encode())


def client_ip(request: Request) -> str:
    """The visitor's address. Behind the proxy every request arrives from the tunnel (127.0.0.1), so use
    the address the proxy reports, but only when the secret proves the header wasn't forged."""
    if from_proxy(request):
        ip = request.headers.get("x-roadwatch-client-ip", "").strip()
        if ip and len(ip) <= 45:
            return ip
    return request.client.host if request.client else "?"


def _new_session(c: sqlite3.Connection, user_id: str, resp: Response, request: Request) -> None:
    token = secrets.token_urlsafe(32)
    now = time.time()
    c.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
              (_th(token), user_id, now, now + SESSION_S))
    https = SECURE_COOKIE or (from_proxy(request) and request.headers.get("x-roadwatch-proto") == "https")
    resp.set_cookie(COOKIE, token, max_age=SESSION_S, httponly=True, samesite="lax", secure=https, path="/")


def current_user(request: Request) -> sqlite3.Row | None:
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        return None
    with db() as c:
        return c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                         "WHERE s.token_hash=? AND s.expires_at>? AND u.disabled=0",
                         (_th(token), time.time())).fetchone()


def require_user(request: Request) -> sqlite3.Row:
    u = current_user(request)
    if u is None:
        raise HTTPException(401, "login required")
    return u


def require_role(*roles: str):
    def dep(u: sqlite3.Row = Depends(require_user)) -> sqlite3.Row:
        if u["role"] not in roles and u["role"] != "admin":
            raise HTTPException(403, "not allowed")
        return u
    return dep


def require_json(request: Request) -> None:
    """CSRF defence in depth: a cross-site <form> can't send application/json without a CORS preflight."""
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(415, "send JSON")


def _throttle(key: str, limit: int | None = None, record: bool = True) -> None:
    """At most `limit` (default LOGIN_LIMIT) hits on `key` per LOGIN_WINDOW_S. record=False only checks."""
    now = time.time()
    limit = LOGIN_LIMIT if limit is None else limit
    with _att_lock:
        a = _attempts[key] = [t for t in _attempts[key] if now - t < LOGIN_WINDOW_S]
        if len(a) >= limit:
            raise HTTPException(429, "too many attempts, try again later")
        if record:
            a.append(now)
        if len(_attempts) > 50_000:   # keep the table bounded: drop keys with no recent hits
            for k in [k for k, v in _attempts.items() if not v or now - v[-1] >= LOGIN_WINDOW_S]:
                del _attempts[k]


def throttle(key: str, limit: int) -> None:
    """Public rate limit for other modules (feedback, reports)."""
    _throttle(key, limit)


def _record_failure(key: str) -> None:
    with _att_lock:
        _attempts[key].append(time.time())


_ip = client_ip


# --------------------------------------------------------------------------- public shapes
def me_json(u: sqlite3.Row) -> dict:
    return {"id": u["id"], "email": u["email"], "display_name": u["display_name"], "phone": u["phone"],
            "role": u["role"], "privacy": privacy_json(u)}


def privacy_json(u: sqlite3.Row) -> dict:
    return {k: bool(u[k]) for k in ("show_name", "profile_public", "share_contact", "show_locations")}


def uploader_json(c: sqlite3.Connection, user_id: str | None) -> dict | None:
    """What anyone may see about a video's uploader: a name only if they chose to show it."""
    if not user_id:
        return None
    u = c.execute("SELECT id, display_name, show_name, profile_public FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        return None
    named = bool(u["show_name"])
    return {"name": u["display_name"] if named else None,
            "profile_id": u["id"] if named and u["profile_public"] else None}


def _contact(u: sqlite3.Row | None) -> dict | None:
    if u is None or not u["share_contact"]:
        return None
    return {"email": u["email"], "phone": u["phone"]}


# --------------------------------------------------------------------------- auth routes
class Signup(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(min_length=1, max_length=60)


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@router.post("/api/auth/signup", dependencies=[Depends(require_json)])
def signup(s: Signup, request: Request, response: Response):
    _throttle(f"signup:{_ip(request)}")
    email = s.email.strip().lower()
    name = s.display_name.strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "invalid email")
    if not name:
        raise HTTPException(400, "name is required")
    uid = uuid.uuid4().hex
    with db() as c:
        try:
            c.execute("INSERT INTO users(id, email, password_hash, display_name, created_at) VALUES (?,?,?,?,?)",
                      (uid, email, hash_password(s.password), name, time.time()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "an account with this email already exists")
        _new_session(c, uid, response, request)
        return me_json(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


@router.post("/api/auth/login", dependencies=[Depends(require_json)])
def login(body: Login, request: Request, response: Response):
    email = body.email.strip().lower()
    ip = _ip(request)
    _throttle(f"login-ip:{ip}")
    # Per-account limits count FAILED attempts only, and the shared one is high: someone who knows your email
    # can't lock you out from one address, while password guessing spread over many addresses still stops.
    _throttle(f"login-fail:{ip}:{email}", record=False)
    _throttle(f"login-fail:{email}", EMAIL_FAIL_LIMIT, record=False)
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        ok = check_password(body.password, u["password_hash"] if u else _DUMMY_HASH)
        if not (u and ok):
            _record_failure(f"login-fail:{ip}:{email}")
            _record_failure(f"login-fail:{email}")
            raise HTTPException(401, "email or password is wrong")   # same answer for unknown emails
        if u["disabled"]:
            raise HTTPException(403, "this account has been disabled")
        _new_session(c, u["id"], response, request)
        return me_json(u)


@router.post("/api/auth/logout", dependencies=[Depends(require_json)])   # no cross-site forced logout
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (_th(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/api/me")
def me(request: Request):
    u = current_user(request)
    return {"user": me_json(u) if u else None}


class Privacy(BaseModel):
    show_name: bool | None = None
    profile_public: bool | None = None
    share_contact: bool | None = None
    show_locations: bool | None = None


class MeUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=20)
    privacy: Privacy | None = None


@router.patch("/api/me", dependencies=[Depends(require_json)])
def update_me(body: MeUpdate, u: sqlite3.Row = Depends(require_user)):
    sets: dict[str, object] = {}
    if body.display_name is not None:
        if not body.display_name.strip():
            raise HTTPException(400, "name is required")
        sets["display_name"] = body.display_name.strip()
    if body.phone is not None:
        phone = body.phone.strip()
        if phone and not PHONE_RE.match(phone):
            raise HTTPException(400, "invalid phone number")
        sets["phone"] = phone or None
    if body.privacy is not None:
        for k, v in body.privacy.model_dump(exclude_none=True).items():
            sets[k] = int(v)
    if sets:   # column names come from the fixed model fields above, never from the client
        with db() as c:
            c.execute(f"UPDATE users SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), u["id"]))
    with db() as c:
        return me_json(c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone())


class PasswordChange(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(min_length=10, max_length=200)


@router.post("/api/me/password", dependencies=[Depends(require_json)])
def change_password(body: PasswordChange, request: Request, response: Response, u: sqlite3.Row = Depends(require_user)):
    _throttle(f"login-email:{u['email']}")
    if not check_password(body.current, u["password_hash"]):
        raise HTTPException(401, "current password is wrong")
    with db() as c:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.new), u["id"]))
        c.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))   # log out everywhere else
        c.execute("DELETE FROM password_resets WHERE user_id=?", (u["id"],))
        _new_session(c, u["id"], response, request)
    return {"ok": True}


# --------------------------------------------------------------------------- forgotten passwords
# A reset link carries a one-time 256-bit token (only its SHA-256 is stored). It is emailed when SMTP is set up;
# otherwise an admin can create one for a user from the admin panel and pass it on (WhatsApp, in person, ...).
RESET_S = 30 * 60               # emailed links: 30 min
ADMIN_RESET_S = 24 * 3600       # admin-made links: 24 h (handed over by a person, so allow longer)
# The link's site address comes from config, never from the request's Host header (host-header poisoning).
PUBLIC_URL = os.environ.get("ROADWATCH_PUBLIC_URL", "http://localhost:3000").rstrip("/")
SMTP = {k: os.environ.get(f"ROADWATCH_SMTP_{k.upper()}", "") for k in ("host", "port", "user", "password", "sender")}


def email_enabled() -> bool:
    return bool(SMTP["host"] and SMTP["sender"])


def create_reset(c: sqlite3.Connection, user_id: str, ttl_s: int, created_by: str | None = None) -> str:
    """New one-time token for user_id; older unused links for that user stop working."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    c.execute("DELETE FROM password_resets WHERE user_id=? OR expires_at<?", (user_id, now))
    c.execute("INSERT INTO password_resets(token_hash, user_id, created_at, expires_at, created_by) VALUES (?,?,?,?,?)",
              (_th(token), user_id, now, now + ttl_s, created_by))
    return token


def reset_path(token: str) -> str:
    return f"/reset?token={token}"


def _send_reset_email(to: str, name: str, link: str) -> None:
    import smtplib
    from email.message import EmailMessage
    m = EmailMessage()
    m["Subject"] = "RoadWatch BD: reset your password"
    m["From"], m["To"] = SMTP["sender"], to
    m.set_content(f"Hello {name},\n\nSomeone (hopefully you) asked to reset the password of your RoadWatch BD "
                  f"account. Open this link within 30 minutes to choose a new password:\n\n{link}\n\n"
                  "If it wasn't you, ignore this email: your password stays the same.\n")
    try:
        port = int(SMTP["port"] or 587)
        cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with cls(SMTP["host"], port, timeout=20) as s:
            if port != 465:
                s.starttls()
            if SMTP["user"]:
                s.login(SMTP["user"], SMTP["password"])
            s.send_message(m)
    except Exception as e:   # never surfaces to the visitor (that would reveal whether the email exists)
        print(f"[accounts] reset email to user failed: {type(e).__name__}: {e}", flush=True)


class Forgot(BaseModel):
    email: str = Field(max_length=254)


@router.post("/api/auth/forgot", dependencies=[Depends(require_json)])
def forgot(body: Forgot, request: Request):
    email = body.email.strip().lower()
    _throttle(f"forgot-ip:{_ip(request)}")
    _throttle(f"forgot-email:{email}")
    if email_enabled():
        with db() as c:
            u = c.execute("SELECT id, display_name FROM users WHERE email=? AND disabled=0", (email,)).fetchone()
            token = create_reset(c, u["id"], RESET_S) if u else None
        if u:   # send in the background: same response time whether or not the account exists
            threading.Thread(target=_send_reset_email, daemon=True,
                             args=(email, u["display_name"], PUBLIC_URL + reset_path(token))).start()
    # Same answer for every email, so this can't be used to find out who has an account.
    return {"ok": True, "email_enabled": email_enabled()}


class Reset(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    new: str = Field(min_length=10, max_length=200)


@router.post("/api/auth/reset", dependencies=[Depends(require_json)])
def reset(body: Reset, request: Request, response: Response):
    _throttle(f"reset-ip:{_ip(request)}")
    now = time.time()
    with db() as c:
        r = c.execute("SELECT r.user_id FROM password_resets r JOIN users u ON u.id = r.user_id "
                      "WHERE r.token_hash=? AND r.used_at IS NULL AND r.expires_at>? AND u.disabled=0",
                      (_th(body.token), now)).fetchone()
        if not r:
            raise HTTPException(400, "this reset link is invalid or has expired")
        uid = r["user_id"]
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.new), uid))
        c.execute("DELETE FROM password_resets WHERE user_id=?", (uid,))   # one use; other links die too
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))          # whoever was logged in is logged out
        _new_session(c, uid, response, request)
        return me_json(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


@router.get("/api/me/videos")
def my_videos(u: sqlite3.Row = Depends(require_user)):
    with db() as c:
        rows = c.execute("SELECT v.id, v.status, v.camera_type, v.created_at, v.lat, v.lng, v.duration_s, "
                         "(SELECT COUNT(*) FROM cases WHERE video_id=v.id) AS cases "
                         "FROM videos v WHERE v.user_id=? ORDER BY v.created_at DESC LIMIT 200", (u["id"],)).fetchall()
    return {"videos": [dict(r) for r in rows]}


def _case_json(c: sqlite3.Connection, r: sqlite3.Row, *, staff: bool) -> dict:
    e = c.execute("SELECT type, vehicle_class, start_s, end_s, confidence, reason FROM events WHERE id=?",
                  (r["event_id"],)).fetchone()
    out = {k: r[k] for k in ("id", "event_id", "video_id", "status", "uploader_note", "created_at", "review_note",
                             "reviewed_at", "fine_bdt", "decided_at")}
    out["event"] = dict(e) if e else None
    # which law the flagged event breaks and its legal maximum fine (a suggestion: staff confirm every case)
    out["law"] = fine_rules.for_event(e["type"] if e else None)
    if staff:   # reviewers/police: contact only if the uploader opted in
        up = c.execute("SELECT * FROM users WHERE id=?", (r["uploader_id"],)).fetchone()
        out["police_ref"] = r["police_ref"]
        out["uploader"] = {"name": up["display_name"] if up and up["show_name"] else None, "contact": _contact(up)}
    return out


@router.get("/api/me/cases")
def my_cases(u: sqlite3.Row = Depends(require_user)):
    with db() as c:
        rows = c.execute("SELECT * FROM cases WHERE uploader_id=? ORDER BY created_at DESC LIMIT 500",
                         (u["id"],)).fetchall()
        return {"cases": [_case_json(c, r, staff=False) for r in rows]}


@router.get("/api/me/rewards")
def my_rewards(u: sqlite3.Row = Depends(require_user)):
    with db() as c:
        rows = c.execute("SELECT id, case_id, fine_bdt, amount_bdt, status, created_at FROM rewards WHERE user_id=? "
                         "ORDER BY created_at DESC", (u["id"],)).fetchall()
    return {"rewards": [dict(r) for r in rows], "share": REWARD_SHARE,
            "total_credited_bdt": sum(r["amount_bdt"] for r in rows if r["status"] == "credited"), "paid_out_bdt": 0}


@router.get("/api/users/{uid}")
def public_profile(uid: str, request: Request):
    viewer = current_user(request)
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u or u["disabled"] or not (u["profile_public"] or (viewer and viewer["id"] == uid)):
            raise HTTPException(404)   # a hidden profile looks the same as a missing one
        vids = c.execute("SELECT id, created_at, camera_type, lat, lng FROM videos WHERE user_id=? AND status='done' "
                         "AND COALESCE(moderation_status, '') != 'hidden' "
                         "ORDER BY created_at DESC LIMIT 100", (uid,)).fetchall()
        confirmed = c.execute("SELECT COUNT(*) FROM cases WHERE uploader_id=? AND status IN ('confirmed','fined')",
                              (uid,)).fetchone()[0]
    locs = bool(u["show_locations"])
    return {"id": u["id"], "display_name": u["display_name"], "member_since": u["created_at"],
            "uploads": len(vids), "confirmed_reports": confirmed,
            "videos": [{"id": v["id"], "created_at": v["created_at"], "camera_type": v["camera_type"],
                        **({"lat": v["lat"], "lng": v["lng"]} if locs and v["lat"] is not None else {})}
                       for v in vids]}


# --------------------------------------------------------------------------- cases
class CaseCreate(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


@router.post("/api/events/{eid}/case", dependencies=[Depends(require_json)])
def submit_case(eid: str, body: CaseCreate, u: sqlite3.Row = Depends(require_user)):
    with db() as c:
        e = c.execute("SELECT e.id, e.type, e.video_id, e.details, v.user_id FROM events e "
                      "JOIN videos v ON v.id = e.video_id WHERE e.id=?", (eid,)).fetchone()
        if not e or e["user_id"] != u["id"]:
            raise HTTPException(404)   # only the uploader can submit their own video's events
        if e["type"] not in CASE_TYPES:
            raise HTTPException(400, "this kind of event can't be reported")
        cid = uuid.uuid4().hex
        try:
            c.execute("INSERT INTO cases(id, event_id, video_id, uploader_id, status, uploader_note, created_at) "
                      "VALUES (?,?,?,?,?,?,?)", (cid, eid, e["video_id"], u["id"], "submitted",
                                                 (body.note or "").strip() or None, time.time()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "already submitted")
    return {"id": cid, "status": "submitted"}


@router.get("/api/review/cases")
def review_queue(status: str = "submitted", u: sqlite3.Row = Depends(require_role("reviewer"))):
    if status not in ("submitted", "confirmed", "rejected", "fined", "dismissed"):
        raise HTTPException(400, "unknown status")
    with db() as c:
        rows = c.execute("SELECT * FROM cases WHERE status=? ORDER BY created_at LIMIT 200", (status,)).fetchall()
        return {"cases": [_case_json(c, r, staff=True) | {"own": r["uploader_id"] == u["id"]} for r in rows]}


class ReviewDecision(BaseModel):
    decision: Literal["confirm", "reject"]
    note: str | None = Field(default=None, max_length=1000)


@router.post("/api/review/cases/{cid}", dependencies=[Depends(require_json)])
def review_case(cid: str, d: ReviewDecision, u: sqlite3.Row = Depends(require_role("reviewer"))):
    with db() as c:
        r = c.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
        if not r:
            raise HTTPException(404)
        if r["uploader_id"] == u["id"]:
            raise HTTPException(403, "you can't review your own report")
        status = "confirmed" if d.decision == "confirm" else "rejected"
        n = c.execute("UPDATE cases SET status=?, reviewer_id=?, review_note=?, reviewed_at=? "
                      "WHERE id=? AND status='submitted'",
                      (status, u["id"], (d.note or "").strip() or None, time.time(), cid)).rowcount
        if n == 0:
            raise HTTPException(409, "already reviewed")
        if status == "confirmed":   # a human confirmed the AI: mark the event verified
            c.execute("UPDATE events SET verified=1 WHERE id=?", (r["event_id"],))
    return {"id": cid, "status": status}


@router.get("/api/police/cases")
def police_queue(status: str = "confirmed", u: sqlite3.Row = Depends(require_role("police"))):
    if status not in ("confirmed", "fined", "dismissed"):
        raise HTTPException(400, "unknown status")
    with db() as c:
        rows = c.execute("SELECT * FROM cases WHERE status=? ORDER BY reviewed_at LIMIT 200", (status,)).fetchall()
        return {"cases": [_case_json(c, r, staff=True) for r in rows]}


class PoliceDecision(BaseModel):
    decision: Literal["fined", "dismissed"]
    fine_bdt: int | None = Field(default=None, ge=1, le=MAX_FINE_BDT)
    police_ref: str | None = Field(default=None, max_length=100)


@router.post("/api/police/cases/{cid}", dependencies=[Depends(require_json)])
def police_decide(cid: str, d: PoliceDecision, u: sqlite3.Row = Depends(require_role("police"))):
    if d.decision == "fined" and not d.fine_bdt:
        raise HTTPException(400, "fine amount is required")
    with db() as c:
        r = c.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
        if not r:
            raise HTTPException(404)
        if r["uploader_id"] == u["id"]:
            raise HTTPException(403, "you can't decide your own report")
        fine = d.fine_bdt if d.decision == "fined" else None
        if fine:   # never above what the Road Transport Act 2018 allows for this offence
            ev = c.execute("SELECT type FROM events WHERE id=?", (r["event_id"],)).fetchone()
            law = fine_rules.for_event(ev["type"] if ev else None)
            if law and fine > law["max_bdt"]:
                raise HTTPException(400, f"the legal maximum for this offence is Tk {law['max_bdt']:,} "
                                         f"(s.{law['penalty']}, Road Transport Act 2018)")
        n = c.execute("UPDATE cases SET status=?, police_id=?, police_ref=?, fine_bdt=?, decided_at=? "
                      "WHERE id=? AND status='confirmed'",
                      (d.decision, u["id"], (d.police_ref or "").strip() or None, fine, time.time(), cid)).rowcount
        if n == 0:
            raise HTTPException(409, "case is not waiting for a police decision")
        reward = None
        if fine:   # same transaction as the status change: one credit per case (rewards.case_id is UNIQUE)
            reward = int(round(fine * REWARD_SHARE))
            c.execute("INSERT INTO rewards(id, user_id, case_id, fine_bdt, amount_bdt, status, created_at) "
                      "VALUES (?,?,?,?,?,?,?)", (uuid.uuid4().hex, r["uploader_id"], cid, fine, reward,
                                                 "credited", time.time()))
    return {"id": cid, "status": d.decision, "reward_bdt": reward}


# --------------------------------------------------------------------------- admin
class RoleChange(BaseModel):
    role: Literal["user", "reviewer", "police", "admin"]


@router.post("/api/admin/users/{uid}/role", dependencies=[Depends(require_json)])
def set_role_route(uid: str, body: RoleChange, u: sqlite3.Row = Depends(require_role("admin"))):
    if uid == u["id"] and body.role != "admin":
        raise HTTPException(400, "you can't remove your own admin role")
    if not set_role(uid, body.role):
        raise HTTPException(404)
    audit(u["id"], "set_role", uid, body.role)
    return {"id": uid, "role": body.role}


def audit(admin_id: str, action: str, target: str | None = None, detail: str | None = None) -> None:
    with db() as c:
        c.execute("INSERT INTO admin_log(id, admin_id, action, target, detail, created_at) VALUES (?,?,?,?,?,?)",
                  (uuid.uuid4().hex, admin_id, action, target, (detail or "")[:500] or None, time.time()))


def set_role(uid: str, role: str) -> bool:
    assert role in ROLES
    with db() as c:
        n = c.execute("UPDATE users SET role=? WHERE id=?", (role, uid)).rowcount
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))   # privilege change: log in again
    return n > 0

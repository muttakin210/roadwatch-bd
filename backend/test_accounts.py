"""Accounts, privacy and the verified-report workflow.  cd backend && python -m pytest -q"""
import importlib
import json
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ROADWATCH_DATA", str(tmp_path))
    sys.path.insert(0, str(Path(__file__).parent))
    app_mod = importlib.reload(importlib.import_module("app"))

    def fake_run_video(path, out_dir, hints, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "events.json").write_text("{}")
        return {"duration_s": 60, "camera_motion": "static", "model_version": "fake", "rules_version": "t",
                "congestion": {"avg": 10}, "summary": {},
                "events": [{"type": "wrong_way", "vehicle_class": "motorcycle", "track": 1, "start": 1.0, "end": 5.0,
                            "raw_score": 0.8, "confidence": 0.8, "reason": "x", "details": {"shown": True}},
                           {"type": "congestion_jam", "start": 0.0, "end": 30.0, "raw_score": 0.9,
                            "confidence": 0.9, "reason": "y", "details": {"shown": True}}]}

    import roadwatch.pipeline
    monkeypatch.setattr(roadwatch.pipeline, "run_video", fake_run_video)
    monkeypatch.setattr(app_mod, "_get_detector", lambda: None)
    from fastapi.testclient import TestClient
    return app_mod, (lambda: TestClient(app_mod.app))


def signup(c, email, name="Rahim", pw="correct horse battery"):
    r = c.post("/api/auth/signup", json={"email": email, "password": pw, "display_name": name})
    assert r.status_code == 200, r.text
    return r.json()


def upload(c):
    up = c.post("/api/uploads", json={"size": 3}).json()
    c.put(f"/api/uploads/{up['id']}?offset=0", content=b"abc")
    vid = c.post("/api/videos", json={"upload_id": up["id"], "lat": 23.75, "lng": 90.39}).json()["id"]
    for _ in range(50):
        if c.get(f"/api/videos/{vid}").json()["status"] == "done":
            return vid
        time.sleep(0.1)
    raise AssertionError("not processed")


def test_signup_login_logout_and_password_storage(env):
    app_mod, client = env
    c = client()
    me = signup(c, "Rahim@Example.com")
    assert me["email"] == "rahim@example.com" and me["role"] == "user"
    assert not any(me["privacy"].values())                    # everything hidden by default
    assert c.get("/api/me").json()["user"]["id"] == me["id"]
    with app_mod.db() as db:
        row = db.execute("SELECT password_hash FROM users").fetchone()
        tok = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert row[0].startswith("scrypt$") and "correct horse" not in row[0]
    assert c.cookies.get("rw_session") not in (None, tok)      # only the hash is stored

    assert c.post("/api/auth/signup", json={"email": "rahim@example.com", "password": "x" * 12,
                                            "display_name": "x"}).status_code == 409
    assert c.post("/api/auth/signup", json={"email": "a@b.co", "password": "short", "display_name": "x"}).status_code == 422
    c.post("/api/auth/logout")
    assert c.get("/api/me").json()["user"] is None
    # the old cookie is dead server-side, not just deleted in the browser
    c.cookies.set("rw_session", "replayed-token")
    assert c.get("/api/me").json()["user"] is None

    bad = c.post("/api/auth/login", json={"email": "rahim@example.com", "password": "wrong password"})
    unknown = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong password"})
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()
    assert c.post("/api/auth/login", json={"email": "RAHIM@example.com",
                                           "password": "correct horse battery"}).status_code == 200


def test_login_is_rate_limited_and_requires_json(env):
    _, client = env
    c = client()
    signup(c, "k@example.com")
    codes = [c.post("/api/auth/login", json={"email": "k@example.com", "password": "nope nope"}).status_code
             for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[-1] == 429
    # a cross-site HTML form can only send form encoding: refused
    assert c.post("/api/auth/signup", data={"email": "f@example.com", "password": "x" * 12,
                                            "display_name": "f"}).status_code == 415


def test_privacy_controls(env):
    _, client = env
    c, other = client(), client()
    me = signup(c, "p@example.com", name="Karim")
    vid = upload(c)
    v = c.get(f"/api/videos/{vid}").json()
    assert v["is_owner"] and v["uploader"] == {"name": None, "profile_id": None}     # anonymous by default
    assert other.get(f"/api/videos/{vid}").json()["is_owner"] is False
    assert other.get(f"/api/users/{me['id']}").status_code == 404                       # hidden profile
    assert c.get(f"/api/users/{me['id']}").status_code == 200                           # but I can see mine

    r = c.patch("/api/me", json={"phone": "+880 1711-000000",
                                 "privacy": {"show_name": True, "profile_public": True}})
    assert r.status_code == 200 and r.json()["privacy"]["show_name"]
    assert other.get(f"/api/videos/{vid}").json()["uploader"] == {"name": "Karim", "profile_id": me["id"]}
    prof = other.get(f"/api/users/{me['id']}").json()
    assert prof["display_name"] == "Karim" and prof["uploads"] == 1
    assert "lat" not in prof["videos"][0]                                               # pins hidden
    assert "email" not in json.dumps(prof) and "1711" not in json.dumps(prof)           # contact never public
    c.patch("/api/me", json={"privacy": {"show_locations": True}})
    assert other.get(f"/api/users/{me['id']}").json()["videos"][0]["lat"] == 23.75

    assert c.patch("/api/me", json={"phone": "call me"}).status_code == 400
    assert c.patch("/api/me", json={"privacy": {"role": "admin"}}).json()["role"] == "user"  # can't self-promote
    assert other.patch("/api/me", json={"display_name": "x"}).status_code == 401


def test_report_review_police_reward_flow(env):
    app_mod, client = env
    import accounts
    up, rev, pol, stranger = client(), client(), client(), client()
    me = signup(up, "uploader@example.com")
    r_id = signup(rev, "reviewer@example.com")["id"]
    p_id = signup(pol, "police@example.com")["id"]
    signup(stranger, "stranger@example.com")
    accounts.set_role(r_id, "reviewer")
    accounts.set_role(p_id, "police")
    # role change ended their sessions: they must log in again to get the new role
    assert rev.get("/api/review/cases").status_code == 401
    for c, e in ((rev, "reviewer@example.com"), (pol, "police@example.com")):
        assert c.post("/api/auth/login", json={"email": e, "password": "correct horse battery"}).status_code == 200

    vid = upload(up)
    evs = up.get(f"/api/videos/{vid}/events").json()["events"]
    ww = next(e for e in evs if e["type"] == "wrong_way")
    jam = next(e for e in evs if e["type"] == "congestion_jam")
    assert ww["reportable"] and not jam["reportable"] and ww["case_status"] is None

    assert stranger.post(f"/api/events/{ww['id']}/case", json={}).status_code == 404   # not their video
    assert up.post(f"/api/events/{jam['id']}/case", json={}).status_code == 400        # not an offence
    case = up.post(f"/api/events/{ww['id']}/case", json={"note": "Farmgate, 9 am"}).json()
    assert up.post(f"/api/events/{ww['id']}/case", json={}).status_code == 409         # once per event

    assert stranger.get("/api/review/cases").status_code == 403
    assert up.post(f"/api/review/cases/{case['id']}", json={"decision": "confirm"}).status_code == 403
    q = rev.get("/api/review/cases").json()["cases"]
    assert [x["id"] for x in q] == [case["id"]] and q[0]["uploader"]["contact"] is None  # contact not shared
    up.patch("/api/me", json={"phone": "01711000000", "privacy": {"share_contact": True}})
    q = rev.get("/api/review/cases").json()["cases"]
    assert q[0]["uploader"]["contact"] == {"email": "uploader@example.com", "phone": "01711000000"}

    # police can't act before a reviewer confirms
    assert pol.post(f"/api/police/cases/{case['id']}", json={"decision": "fined", "fine_bdt": 5000}).status_code == 409
    assert rev.post(f"/api/review/cases/{case['id']}", json={"decision": "confirm"}).json()["status"] == "confirmed"
    assert rev.post(f"/api/review/cases/{case['id']}", json={"decision": "reject"}).status_code == 409
    assert next(e for e in up.get(f"/api/videos/{vid}/events").json()["events"] if e["id"] == ww["id"])["verified"]

    assert rev.post(f"/api/police/cases/{case['id']}", json={"decision": "fined", "fine_bdt": 5000}).status_code == 403
    assert pol.post(f"/api/police/cases/{case['id']}", json={"decision": "fined"}).status_code == 400
    assert pol.post(f"/api/police/cases/{case['id']}",
                    json={"decision": "fined", "fine_bdt": 10 ** 9}).status_code == 422
    r = pol.post(f"/api/police/cases/{case['id']}", json={"decision": "fined", "fine_bdt": 5000, "police_ref": "DMP-1"})
    assert r.json() == {"id": case["id"], "status": "fined", "reward_bdt": 1000}
    assert pol.post(f"/api/police/cases/{case['id']}",
                    json={"decision": "fined", "fine_bdt": 5000}).status_code == 409    # no double credit

    rw = up.get("/api/me/rewards").json()
    assert rw["total_credited_bdt"] == 1000 and rw["paid_out_bdt"] == 0 and len(rw["rewards"]) == 1
    assert stranger.get("/api/me/rewards").json()["total_credited_bdt"] == 0
    mine = up.get("/api/me/cases").json()["cases"]
    assert mine[0]["status"] == "fined" and "police_ref" not in mine[0] and "uploader" not in mine[0]
    assert next(e for e in up.get(f"/api/videos/{vid}/events").json()["events"]
                if e["id"] == ww["id"])["case_status"] == "fined"
    assert "case_status" not in stranger.get(f"/api/videos/{vid}/events").json()["events"][0]


def test_reviewer_cannot_review_own_report_and_admin_roles(env):
    app_mod, client = env
    import accounts
    a = client()
    me = signup(a, "admin@example.com")
    accounts.set_role(me["id"], "admin")
    a.post("/api/auth/login", json={"email": "admin@example.com", "password": "correct horse battery"})
    vid = upload(a)
    ww = next(e for e in a.get(f"/api/videos/{vid}/events").json()["events"] if e["type"] == "wrong_way")
    cid = a.post(f"/api/events/{ww['id']}/case", json={}).json()["id"]
    assert a.post(f"/api/review/cases/{cid}", json={"decision": "confirm"}).status_code == 403

    b = client()
    bid = signup(b, "b@example.com")["id"]
    assert b.post(f"/api/admin/users/{bid}/role", json={"role": "admin"}).status_code == 403
    assert a.post(f"/api/admin/users/{bid}/role", json={"role": "reviewer"}).json()["role"] == "reviewer"
    assert a.post(f"/api/admin/users/{me['id']}/role", json={"role": "user"}).status_code == 400
    assert a.post(f"/api/admin/users/{bid}/role", json={"role": "god"}).status_code == 422
    assert b.get("/api/me").json()["user"] is None                 # promoted user was logged out

    # anonymous uploads keep working, but an owned video can only be re-analysed by its owner
    assert b.post(f"/api/videos/{vid}/reanalyse").status_code == 403

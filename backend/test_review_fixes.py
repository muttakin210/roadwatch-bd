"""Regression tests for the 2026-11-06 review fixes.  cd backend && python -m pytest -q"""
import json
import time

from test_accounts import env, signup, upload  # noqa: F401  (pytest fixture + helpers)


def _wait_done(c, vid):
    for _ in range(50):
        if c.get(f"/api/videos/{vid}").json()["status"] in ("done", "failed"):
            return
        time.sleep(0.1)
    raise AssertionError("not processed")


def _admin(client):
    import accounts
    a = client()
    aid = signup(a, "boss@example.com")["id"]
    accounts.set_role(aid, "admin")
    a.post("/api/auth/login", json={"email": "boss@example.com", "password": "correct horse battery"})
    return a


def test_raw_upload_is_deleted_after_retention_unless_consented(env):
    app_mod, client = env
    c = client()
    signup(c, "u@example.com")
    old, kept = upload(c), upload(c)
    with app_mod.db() as db:
        db.execute("UPDATE videos SET created_at=? WHERE id IN (?,?)", (time.time() - 40 * 86400, old, kept))
        db.execute("UPDATE videos SET consent_training=1 WHERE id=?", (kept,))
        keys = dict(db.execute("SELECT id, storage_key FROM videos").fetchall())
    assert app_mod.housekeeping()["raw_deleted"] == 1
    assert not (app_mod.UPLOADS / keys[old]).exists() and (app_mod.UPLOADS / keys[kept]).exists()
    with app_mod.db() as db:
        assert db.execute("SELECT raw_deleted_at FROM videos WHERE id=?", (old,)).fetchone()[0] is not None
    assert c.get(f"/api/videos/{old}/annotated").status_code in (200, 404)        # results stay
    assert c.post(f"/api/videos/{old}/reanalyse").status_code == 409              # nothing left to analyse
    assert app_mod.housekeeping()["raw_deleted"] == 0                              # done once


def test_abandoned_partial_uploads_are_cleaned_up(env):
    app_mod, client = env
    c = client()
    uid = c.post("/api/uploads", json={"size": 10}).json()["id"]
    fresh = c.post("/api/uploads", json={"size": 10}).json()["id"]
    meta = app_mod.PARTIAL / f"{uid}.json"
    meta.write_text(json.dumps({"size": 10, "created": time.time() - 2 * 86400}))
    assert app_mod.housekeeping()["partials_deleted"] == 1
    assert not meta.exists() and not (app_mod.PARTIAL / f"{uid}.part").exists()
    assert (app_mod.PARTIAL / f"{fresh}.json").exists()


def test_unfinished_jobs_are_requeued_after_a_restart(env):
    app_mod, client = env
    c = client()
    vid = upload(c)
    with app_mod.db() as db:
        db.execute("UPDATE videos SET status='processing' WHERE id=?", (vid,))   # the process died mid-job
    app_mod._progress.clear()
    assert app_mod.recover_jobs() == 1
    _wait_done(c, vid)
    assert c.get(f"/api/videos/{vid}").json()["status"] == "done"


def test_anonymous_videos_can_only_be_reanalysed_by_staff(env):
    _, client = env
    anon = client()
    vid = upload(anon)
    assert anon.post(f"/api/videos/{vid}/reanalyse").status_code == 403
    other = client()
    signup(other, "o@example.com")
    assert other.post(f"/api/videos/{vid}/reanalyse").status_code == 403
    a = _admin(client)
    assert a.post(f"/api/admin/videos/{vid}/reanalyse", json={}).status_code == 200


def test_reanalysis_does_not_duplicate_map_incidents_or_hide_cases(env):
    _, client = env
    c = client()
    signup(c, "u@example.com")
    vid = upload(c)
    inc = lambda: [i["type"] for i in client().get("/api/map/incidents").json()["incidents"]]  # noqa: E731
    assert inc() == ["congestion_jam"]
    ww = next(e for e in c.get(f"/api/videos/{vid}/events").json()["events"] if e["type"] == "wrong_way")
    assert c.post(f"/api/events/{ww['id']}/case", json={}).status_code == 200
    assert c.post(f"/api/videos/{vid}/reanalyse").status_code == 200
    _wait_done(c, vid)
    assert inc() == ["congestion_jam"]                                         # not two jams
    evs = c.get(f"/api/videos/{vid}/events").json()["events"]
    assert any(e["id"] == ww["id"] and e["case_status"] == "submitted" for e in evs)   # the case is still visible


def test_hints_and_location_are_validated(env):
    _, client = env
    c = client()

    def create(**body):
        up = c.post("/api/uploads", json={"size": 3}).json()
        c.put(f"/api/uploads/{up['id']}?offset=0", content=b"abc")
        return c.post("/api/videos", json={"upload_id": up["id"], **body})

    assert create(hints={"arrows": [[1, 2, 3]]}).status_code == 400
    assert create(hints={"arrows": [[1, 2, 3, 4]] * 21}).status_code == 400
    assert create(hints={"oneway": "yes"}).status_code == 400
    assert create(hints={"trim": [5, 400]}).status_code == 400
    assert create(lat=123.0, lng=90.0).status_code == 400
    assert create(lat=23.7).status_code == 400                                 # both or neither
    assert create(hints={"__class__": 1, "arrows": [[1, 2, 3, 4]], "trim": [2, 30]}).status_code == 200
    assert c.post("/api/videos", files={"file": ("a.mp4", b"x")}, data={"lat": "north"}).status_code == 400


def test_feedback_is_checked_and_rate_limited(env, monkeypatch):
    app_mod, client = env
    c = client()
    vid = upload(c)
    eid = c.get(f"/api/videos/{vid}/events").json()["events"][0]["id"]
    url = f"/api/events/{eid}/feedback"
    assert c.post(url, json={"verdict": "wrong_type", "corrected_type": "x" * 30}).status_code == 400
    assert c.post(url, data={"verdict": "correct"}).status_code == 415        # JSON only
    monkeypatch.setattr(app_mod, "FEEDBACK_LIMIT", 2)
    codes = [c.post(url, json={"verdict": "correct"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_progress_stream_respects_hidden_videos(env):
    _, client = env
    vid = upload(client())
    a = _admin(client)
    assert a.post(f"/api/admin/videos/{vid}/moderation", json={"status": "hidden"}).status_code == 200
    assert client().get(f"/api/videos/{vid}/stream").status_code == 404
    assert client().get("/api/videos/not-a-video-id/stream").status_code == 404


def test_video_deleted_while_queued_leaves_nothing_behind(env):
    app_mod, client = env
    c = client()
    vid = upload(c)
    a = _admin(client)
    with app_mod.db() as db:   # a job for a video that is deleted before the worker picks it up
        db.execute("UPDATE videos SET status='done' WHERE id=?", (vid,))
    assert a.post(f"/api/admin/videos/{vid}/delete", json={"confirm": True, "reason": "test"}).status_code == 200
    app_mod._process(vid, "f" * 32)
    assert not (app_mod.RESULTS / vid).exists()
    with app_mod.db() as db:
        assert db.execute("SELECT COUNT(*) FROM results WHERE video_id=?", (vid,)).fetchone()[0] == 0


def test_in_memory_tables_are_pruned(env):
    app_mod, _ = env
    app_mod._ip_counts[("1.2.3.4", "2000-01-01")] = 5
    app_mod._progress["x" * 32] = {"step": "done", "progress": 1, "at": time.time() - 3600}
    app_mod.housekeeping()
    assert ("1.2.3.4", "2000-01-01") not in app_mod._ip_counts and "x" * 32 not in app_mod._progress

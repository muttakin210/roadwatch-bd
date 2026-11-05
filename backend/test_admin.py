"""Admin panel API.  cd backend && python -m pytest -q"""

from test_accounts import env, signup, upload  # noqa: F401  (pytest fixture + helpers)


def login(c, email):
    assert c.post("/api/auth/login", json={"email": email, "password": "correct horse battery"}).status_code == 200


def make_admin(client, email="boss@example.com"):
    import accounts
    a = client()
    uid = signup(a, email)["id"]
    accounts.set_role(uid, "admin")
    login(a, email)
    return a, uid


def test_only_admins_reach_the_panel(env):
    _, client = env
    u = client()
    signup(u, "plain@example.com")
    anon = client()
    for path in ("stats", "system", "users", "videos", "reports", "cases", "rewards", "log"):
        assert anon.get(f"/api/admin/{path}").status_code == 401
        assert u.get(f"/api/admin/{path}").status_code == 403
    a, _ = make_admin(client)
    for path in ("stats", "system", "users", "videos", "reports", "cases", "rewards", "log"):
        assert a.get(f"/api/admin/{path}").status_code == 200, path


def test_disable_user_logs_them_out_and_blocks_login(env):
    _, client = env
    a, aid = make_admin(client)
    u = client()
    uid = signup(u, "spammer@example.com")["id"]
    assert a.post(f"/api/admin/users/{uid}/disable", json={"disabled": True, "reason": "spam"}).json()["disabled"]
    assert u.get("/api/me").json()["user"] is None
    r = u.post("/api/auth/login", json={"email": "spammer@example.com", "password": "correct horse battery"})
    assert r.status_code == 403
    assert a.post(f"/api/admin/users/{aid}/disable", json={"disabled": True}).status_code == 400   # not yourself
    users = {x["email"]: x for x in a.get("/api/admin/users?q=spammer").json()["users"]}
    assert users["spammer@example.com"]["disabled"] is True
    a.post(f"/api/admin/users/{uid}/disable", json={"disabled": False})
    login(u, "spammer@example.com")
    log = a.get("/api/admin/log").json()["log"]
    assert [x["action"] for x in log][:2] == ["enable_user", "disable_user"] and log[1]["detail"] == "spam"


def test_hide_video_and_viewer_reports(env):
    _, client = env
    a, _ = make_admin(client)
    owner, viewer = client(), client()
    signup(owner, "owner@example.com")
    vid = upload(owner)
    assert viewer.post(f"/api/videos/{vid}/report", json={"reason": "shows a face"}).json()["ok"]
    reps = a.get("/api/admin/reports").json()["reports"]
    assert len(reps) == 1 and reps[0]["video_id"] == vid

    assert a.post(f"/api/admin/videos/{vid}/moderation", json={"status": "hidden", "reason": "face"}).status_code == 200
    for path in ("", "/events", "/annotated", "/events.json"):
        assert viewer.get(f"/api/videos/{vid}{path}").status_code == 404, path
    assert owner.get(f"/api/videos/{vid}").status_code == 200                 # the uploader still sees it
    assert a.get(f"/api/videos/{vid}").status_code == 200
    # a new viewer report must not un-hide it
    viewer.post(f"/api/videos/{vid}/report", json={"reason": "again"})
    assert a.get("/api/admin/videos?moderation=hidden").json()["videos"][0]["id"] == vid

    assert a.post(f"/api/admin/reports/{reps[0]['id']}/resolve", json={}).json()["resolved"]
    assert len(a.get("/api/admin/reports").json()["reports"]) == 1            # only the second one left open
    a.post(f"/api/admin/videos/{vid}/moderation", json={"status": "ok"})
    assert viewer.get(f"/api/videos/{vid}").status_code == 200


def test_delete_video_and_void_reward(env):
    app_mod, client = env
    import accounts
    a, _ = make_admin(client)
    owner, pol, rev = client(), client(), client()
    signup(owner, "o@example.com")
    accounts.set_role(signup(pol, "p@example.com")["id"], "police")
    accounts.set_role(signup(rev, "r@example.com")["id"], "reviewer")
    login(pol, "p@example.com")
    login(rev, "r@example.com")

    # plain delete: files and rows go
    vid = upload(owner)
    res_dir = app_mod.RESULTS / vid
    assert res_dir.exists()
    assert a.post(f"/api/admin/videos/{vid}/delete", json={"reason": "test"}).status_code == 422  # must confirm
    assert a.post(f"/api/admin/videos/{vid}/delete", json={"confirm": True, "reason": "test"}).json()["deleted"]
    assert not res_dir.exists() and owner.get(f"/api/videos/{vid}").status_code == 404
    assert not any(p.name.startswith(vid) for p in app_mod.UPLOADS.iterdir())
    assert a.post("/api/admin/videos/../../etc/delete", json={"confirm": True, "reason": "x" * 3}).status_code == 404

    # a fined video can't be deleted (the ledger refers to it); its reward can be voided
    vid = upload(owner)
    ww = next(e for e in owner.get(f"/api/videos/{vid}/events").json()["events"] if e["type"] == "wrong_way")
    cid = owner.post(f"/api/events/{ww['id']}/case", json={}).json()["id"]
    rev.post(f"/api/review/cases/{cid}", json={"decision": "confirm"})
    pol.post(f"/api/police/cases/{cid}", json={"decision": "fined", "fine_bdt": 2000})
    assert owner.get("/api/me/rewards").json()["total_credited_bdt"] == 400
    assert a.post(f"/api/admin/videos/{vid}/delete", json={"confirm": True, "reason": "test"}).status_code == 409
    assert a.get("/api/admin/stats").json()["rewards_credited_bdt"] == 400
    rid = a.get("/api/admin/rewards").json()["rewards"][0]["id"]
    assert a.post(f"/api/admin/rewards/{rid}/void", json={"reason": "duplicate report"}).json()["status"] == "void"
    assert a.post(f"/api/admin/rewards/{rid}/void", json={"reason": "again"}).status_code == 404
    assert owner.get("/api/me/rewards").json()["total_credited_bdt"] == 0
    assert a.get("/api/admin/cases?status=fined").json()["cases"][0]["id"] == cid
    actions = [x["action"] for x in a.get("/api/admin/log").json()["log"]]
    assert "void_reward" in actions and "delete_video" in actions


def test_system_info(env):
    _, client = env
    a, _ = make_admin(client)
    signup(client(), "x@example.com")
    s = a.get("/api/admin/system").json()
    assert {"detector", "queue", "disk_bytes", "failed_jobs"} <= s.keys()
    st = a.get("/api/admin/stats").json()
    assert st["users"] == {"admin": 1, "user": 1}

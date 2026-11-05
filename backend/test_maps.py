"""Road situation map: what appears publicly, and the offline map pack.  cd backend && python -m pytest -q"""
from test_accounts import env, signup, upload  # noqa: F401  (pytest fixture + helpers)


def _types(c):
    return sorted(i["type"] for i in c.get("/api/map/incidents").json()["incidents"])


def test_jams_show_at_once_but_violations_only_after_review_and_never_when_hidden(env):
    _, client = env
    import accounts
    up, rev, adm, anon = client(), client(), client(), client()
    signup(up, "u@example.com")
    r_id = signup(rev, "r@example.com")["id"]
    a_id = signup(adm, "a@example.com")["id"]
    accounts.set_role(r_id, "reviewer")
    accounts.set_role(a_id, "admin")
    for c, e in ((rev, "r@example.com"), (adm, "a@example.com")):
        c.post("/api/auth/login", json={"email": e, "password": "correct horse battery"})
    vid = upload(up)

    assert _types(anon) == ["congestion_jam"]                       # AI jam estimate: shown; wrong way: not yet
    ww = next(e for e in up.get(f"/api/videos/{vid}/events").json()["events"] if e["type"] == "wrong_way")
    case = up.post(f"/api/events/{ww['id']}/case", json={}).json()
    rev.post(f"/api/review/cases/{case['id']}", json={"decision": "confirm"})
    inc = anon.get("/api/map/incidents").json()["incidents"]
    assert sorted(i["type"] for i in inc) == ["congestion_jam", "wrong_way"]
    assert all(set(i) >= {"lat", "lng", "video_id"} and "user_id" not in i and "email" not in i for i in inc)

    assert adm.post(f"/api/admin/videos/{vid}/moderation", json={"status": "hidden"}).status_code == 200
    assert _types(anon) == []                                       # moderated away: off the map too


def test_offline_pack_is_optional_and_supports_range_requests(env):
    app_mod, client = env
    c = client()
    assert c.get("/api/map/offline").json() == {"available": False}
    assert c.get("/api/map/offline/bd.pmtiles").status_code == 404
    pack = app_mod.DATA / "maps" / "bd.pmtiles"
    pack.parent.mkdir(parents=True, exist_ok=True)
    pack.write_bytes(b"PMTiles" + bytes(range(256)) * 4)
    info = c.get("/api/map/offline").json()
    assert info["available"] and info["bytes"] == pack.stat().st_size
    part = c.get(info["url"], headers={"Range": "bytes=0-6"})
    assert part.status_code == 206 and part.content == b"PMTiles"   # MapLibre reads single tiles this way

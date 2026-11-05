"""Forgotten passwords: emailed one-time links and admin-made links.  cd backend && python -m pytest -q"""
import time

from test_accounts import env, signup  # noqa: F401  (pytest fixture + helpers)

PW, NEW = "correct horse battery", "a brand new password"


def _token(path):
    return path.split("token=", 1)[1]


def test_forgot_gives_the_same_answer_for_every_email(env, monkeypatch):
    _, client = env
    import accounts
    sent = []
    monkeypatch.setattr(accounts, "SMTP", {**accounts.SMTP, "host": "smtp.test", "sender": "rw@test"})
    monkeypatch.setattr(accounts, "_send_reset_email", lambda to, name, link: sent.append((to, link)))
    c = client()
    signup(c, "known@example.com")
    a = c.post("/api/auth/forgot", json={"email": "known@example.com"})
    b = c.post("/api/auth/forgot", json={"email": "nobody@example.com"})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    for _ in range(50):          # the email goes out on a background thread
        if sent:
            break
        time.sleep(0.02)
    assert [s[0] for s in sent] == ["known@example.com"]
    assert sent[0][1].startswith(accounts.PUBLIC_URL + "/reset?token=")   # never built from the Host header


def test_reset_link_works_once_and_logs_out_everywhere(env, monkeypatch):
    _, client = env
    import accounts
    links = []
    monkeypatch.setattr(accounts, "SMTP", {**accounts.SMTP, "host": "smtp.test", "sender": "rw@test"})
    monkeypatch.setattr(accounts, "_send_reset_email", lambda to, name, link: links.append(link))
    old_device, c = client(), client()
    signup(old_device, "r@example.com")
    c.post("/api/auth/forgot", json={"email": "r@example.com"})
    for _ in range(50):
        if links:
            break
        time.sleep(0.02)
    token = _token(links[0])

    assert c.post("/api/auth/reset", json={"token": token, "new": "short"}).status_code == 422
    r = c.post("/api/auth/reset", json={"token": token, "new": NEW})
    assert r.status_code == 200 and r.json()["email"] == "r@example.com"
    assert c.get("/api/me").json()["user"]["email"] == "r@example.com"          # logged in by the reset
    assert old_device.get("/api/me").json()["user"] is None                     # old sessions are gone
    assert c.post("/api/auth/reset", json={"token": token, "new": NEW}).status_code == 400   # one use only
    fresh = client()
    assert fresh.post("/api/auth/login", json={"email": "r@example.com", "password": PW}).status_code == 401
    assert fresh.post("/api/auth/login", json={"email": "r@example.com", "password": NEW}).status_code == 200


def test_expired_or_made_up_tokens_are_refused(env):
    _, client = env
    import accounts
    c = client()
    u = signup(c, "e@example.com")
    with accounts.db() as db:
        token = accounts.create_reset(db, u["id"], ttl_s=-1)
    assert c.post("/api/auth/reset", json={"token": token, "new": NEW}).status_code == 400
    assert c.post("/api/auth/reset", json={"token": "x" * 43, "new": NEW}).status_code == 400


def test_without_email_nothing_is_sent_and_admin_can_make_a_link(env):
    _, client = env
    import accounts
    assert not accounts.email_enabled()
    admin, user, other = client(), client(), client()
    a = signup(admin, "boss@example.com")
    u = signup(user, "forgetful@example.com")
    accounts.set_role(a["id"], "admin")
    admin.post("/api/auth/login", json={"email": "boss@example.com", "password": PW})

    r = other.post("/api/auth/forgot", json={"email": "forgetful@example.com"})
    assert r.json() == {"ok": True, "email_enabled": False}
    with accounts.db() as db:
        assert db.execute("SELECT COUNT(*) FROM password_resets").fetchone()[0] == 0

    assert user.post(f"/api/admin/users/{u['id']}/reset-link", json={}).status_code == 403   # admins only
    r = admin.post(f"/api/admin/users/{u['id']}/reset-link", json={})
    assert r.status_code == 200
    first = r.json()["path"]
    second = admin.post(f"/api/admin/users/{u['id']}/reset-link", json={}).json()["path"]
    assert other.post("/api/auth/reset", json={"token": _token(first), "new": NEW}).status_code == 400  # replaced
    assert other.post("/api/auth/reset", json={"token": _token(second), "new": NEW}).status_code == 200
    log = admin.get("/api/admin/log").json()
    assert any(e["action"] == "reset_link" for e in log.get("log", log.get("entries", [])))


def test_changing_the_password_cancels_open_links(env):
    _, client = env
    import accounts
    c = client()
    u = signup(c, "p@example.com")
    with accounts.db() as db:
        token = accounts.create_reset(db, u["id"], accounts.RESET_S)
    assert c.post("/api/me/password", json={"current": PW, "new": NEW}).status_code == 200
    assert client().post("/api/auth/reset", json={"token": token, "new": "yet another pass"}).status_code == 400

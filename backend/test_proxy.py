"""Public deployment: the backend only answers the web app's proxy.  cd backend && python -m pytest -q"""
from test_accounts import env, signup  # noqa: F401  (pytest fixture + helpers)

SECRET = "s3cret-for-tests"
VIA = {"x-roadwatch-secret": SECRET}


def test_requests_without_the_secret_are_refused(env, monkeypatch):
    _, client = env
    import accounts
    monkeypatch.setattr(accounts, "PROXY_SECRET", SECRET)
    c = client()
    assert c.get("/api/me").status_code == 404                       # straight to the tunnel URL
    assert c.get("/").status_code == 404                             # bare upload page too
    assert c.get("/api/me", headers={"x-roadwatch-secret": "guess"}).status_code == 404
    assert c.get("/api/me", headers=VIA).status_code == 200


def test_rate_limit_uses_the_visitor_ip_reported_by_the_proxy(env, monkeypatch):
    _, client = env
    import accounts
    monkeypatch.setattr(accounts, "PROXY_SECRET", SECRET)
    c = client()
    signup(c.__class__(c.app, headers=VIA), "victim@example.com")

    def attempt(ip, secret=SECRET):
        return c.post("/api/auth/login", json={"email": f"x{ip}@example.com", "password": "wrong wrong"},
                      headers={"x-roadwatch-secret": secret, "x-roadwatch-client-ip": ip}).status_code

    # one visitor hammering login gets blocked ...
    assert [attempt("203.0.113.9") for _ in range(11)][-1] == 429
    # ... but everyone else, who also arrives via the same tunnel, still can log in
    assert attempt("198.51.100.7") == 401
    ok = c.post("/api/auth/login", json={"email": "victim@example.com", "password": "correct horse battery"},
                headers=VIA | {"x-roadwatch-client-ip": "198.51.100.8"})
    assert ok.status_code == 200


def test_secure_cookie_over_https_only(env, monkeypatch):
    _, client = env
    import accounts
    monkeypatch.setattr(accounts, "PROXY_SECRET", SECRET)
    c = client()
    r = c.post("/api/auth/signup", json={"email": "h@example.com", "password": "correct horse battery",
                                         "display_name": "h"}, headers=VIA | {"x-roadwatch-proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()
    r = c.post("/api/auth/signup", json={"email": "l@example.com", "password": "correct horse battery",
                                         "display_name": "l"}, headers=VIA | {"x-roadwatch-proto": "http"})
    assert "secure" not in r.headers["set-cookie"].lower()           # LAN testing over http still works


def test_without_a_secret_forwarded_headers_are_ignored(env):
    _, client = env
    import accounts
    assert accounts.PROXY_SECRET == ""
    c = client()
    # local dev: no secret, so a forged client-ip header can't dodge the limit
    codes = [c.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong wrong"},
                    headers={"x-roadwatch-client-ip": f"10.0.0.{i}"}).status_code for i in range(11)]
    assert codes[-1] == 429

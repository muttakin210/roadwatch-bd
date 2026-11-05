"""Admin tasks that must not be reachable over HTTP.

    python manage.py set-role you@example.com admin     # bootstrap the first admin
    python manage.py set-role reviewer@example.com reviewer
    python manage.py reset-link user@example.com        # one-time password reset path, valid 24 h
"""
import sys

import app  # noqa: F401  (creates the schema and wires accounts.setup)
import accounts


def _user(email: str):
    with app.db() as c:
        return c.execute("SELECT id FROM users WHERE email=?", (email.strip().lower(),)).fetchone()


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "set-role" and argv[2] in accounts.ROLES:
        u = _user(argv[1])
        if not u:
            print("no such user")
            return 1
        accounts.set_role(u["id"], argv[2])
        print(f"{argv[1]} is now {argv[2]} (their sessions were ended; they must log in again)")
        return 0
    if len(argv) == 2 and argv[0] == "reset-link":
        u = _user(argv[1])
        if not u:
            print("no such user")
            return 1
        with app.db() as c:
            token = accounts.create_reset(c, u["id"], accounts.ADMIN_RESET_S, created_by="manage.py")
        # a path, so it works on whichever address the site is opened at (localhost, LAN, Vercel)
        print(accounts.reset_path(token))
        return 0
    print(__doc__.strip(), f"\nroles: {', '.join(accounts.ROLES)}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

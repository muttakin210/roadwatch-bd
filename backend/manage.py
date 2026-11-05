"""Admin tasks that must not be reachable over HTTP.

    python manage.py set-role you@example.com admin     # bootstrap the first admin
    python manage.py set-role reviewer@example.com reviewer
"""
import sys

import app  # noqa: F401  (creates the schema and wires accounts.setup)
import accounts


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "set-role" or argv[2] not in accounts.ROLES:
        print(__doc__.strip(), f"\nroles: {', '.join(accounts.ROLES)}")
        return 2
    with app.db() as c:
        u = c.execute("SELECT id FROM users WHERE email=?", (argv[1].strip().lower(),)).fetchone()
    if not u:
        print("no such user")
        return 1
    accounts.set_role(u["id"], argv[2])
    print(f"{argv[1]} is now {argv[2]} (their sessions were ended; they must log in again)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

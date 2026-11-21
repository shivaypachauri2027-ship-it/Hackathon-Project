"""
Frees PostgreSQL connection slots on Aiven's free plan (20 connections in total).

Use it when you see:  "remaining connection slots are reserved for roles with the SUPERUSER attribute"
That happens when the laptop's Wi-Fi drops: the old connections die on our side,
but Aiven keeps them open, so there are no slots left for new ones.

Run from the backend/ folder (virtual environment active):

    python scripts/free_db_connections.py          list the connections that are open now
    python scripts/free_db_connections.py --kill   close every idle InstaStock connection

Stop the API and the worker (Ctrl+C) before --kill, then start them again.
"""
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets us import app.*

from app.config import DATABASE_URL, is_configured  # noqa: E402

FULL_HELP = """All connection slots are full, so even this script can't get in.
  1. Stop the API and the worker: click each terminal and press Ctrl+C.
  2. Wait 1 minute, then run this again:  python scripts/free_db_connections.py --kill
  3. Still full? Aiven Console -> your PostgreSQL service -> Current queries
     -> Terminate the idle connections, then run this again."""


def main():
    if not is_configured(DATABASE_URL):
        sys.exit("DATABASE_URL is not filled in backend/.env")
    kill = "--kill" in sys.argv

    try:
        conn = psycopg.connect(
            DATABASE_URL, connect_timeout=15, autocommit=True,
            application_name="instastock-cleanup", row_factory=dict_row,
        )
    except psycopg.OperationalError as e:
        if "reserved" in str(e) or "too many" in str(e):
            sys.exit(FULL_HELP)
        sys.exit(f"Could not connect to PostgreSQL: {e}")

    with conn:
        limit = int(conn.execute("SHOW max_connections").fetchone()["max_connections"])
        mine = conn.execute(
            """SELECT pid, COALESCE(NULLIF(application_name, ''), '(no name)') AS program, state,
                      COALESCE(round(extract(epoch FROM now() - state_change))::int, 0) AS seconds
                 FROM pg_stat_activity
                WHERE usename = current_user AND backend_type = 'client backend'
                  AND pid <> pg_backend_pid()
                ORDER BY state_change"""
        ).fetchall()
        total = conn.execute("SELECT count(*) AS n FROM pg_stat_activity WHERE backend_type = 'client backend'").fetchone()["n"]

        print(f"Connections open: {total} of {limit} (Aiven keeps a few of these for itself)")
        print(f"Yours (not counting this script): {len(mine)}\n")
        for row in mine:
            print(f"  pid {row['pid']:>6}  {row['program']:<20} {row['state'] or '?':<22} for {row['seconds']} s")

        if not kill:
            if mine:
                print("\nTo close the idle ones:  python scripts/free_db_connections.py --kill")
            return

        closed = conn.execute(
            """SELECT count(*) FILTER (WHERE pg_terminate_backend(pid)) AS n
                 FROM pg_stat_activity
                WHERE usename = current_user AND backend_type = 'client backend'
                  AND pid <> pg_backend_pid() AND state IS DISTINCT FROM 'active'"""
        ).fetchone()["n"]
        print(f"\nClosed {closed} idle connection(s). Now start the API and the worker again.")


if __name__ == "__main__":
    main()

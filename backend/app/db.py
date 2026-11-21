"""
PostgreSQL connection pool.

Opening a new connection to Aiven (over the internet, with TLS) takes a moment,
so we keep a small pool of open connections and reuse them for every request.
Rows come back as dictionaries, e.g. {"id": 1, "name": "boAt Airdopes 141"}.

Aiven's FREE plan allows only 20 connections in total (Aiven keeps a few for
itself), so every program keeps its pool small:
    API 4  +  worker 3  +  a script 2  =  9
"""
import os
import sys

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL, is_configured

_pool = None

POOL_SIZES = {"instastock-api": 4, "instastock-worker": 3, "instastock-script": 2}

# If the laptop's Wi-Fi drops, the old connections die on our side but Aiven
# can keep them (and their slots) open for HOURS. These keepalives make both
# sides notice a dead connection within about a minute and free the slot.
KEEPALIVES = {
    "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3,   # our side
    "options": "-c tcp_keepalives_idle=30 -c tcp_keepalives_interval=10 -c tcp_keepalives_count=3",  # Aiven's side
}


class DatabaseNotConfigured(RuntimeError):
    pass


def program_name() -> str:
    """Which program is this? Shown in Aiven Console -> Current queries."""
    main = sys.modules.get("__main__")
    spec = getattr(main, "__spec__", None)
    if spec is not None and spec.name == "app.worker":
        return "instastock-worker"
    if "app.main" in sys.modules:
        return "instastock-api"
    return "instastock-script"


def get_pool() -> ConnectionPool:
    global _pool
    if not is_configured(DATABASE_URL):
        raise DatabaseNotConfigured("DATABASE_URL is not filled in backend/.env")
    if _pool is None:
        name = program_name()
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=int(os.getenv("DB_POOL_MAX", POOL_SIZES[name])),
            max_idle=120,           # close extra connections after 2 idle minutes
            timeout=10,             # seconds to wait for a free connection
            kwargs={"row_factory": dict_row, "application_name": name, "connect_timeout": 15, **KEEPALIVES},
            check=ConnectionPool.check_connection,  # replaces connections Aiven closed while idle
            open=True,
        )
    return _pool


def connection():
    """Usage:  with db.connection() as conn: conn.execute(...)
    Leaving the block commits; an exception inside it rolls everything back."""
    return get_pool().connection()


def ping() -> dict:
    """Used by /api/health to show whether PostgreSQL is reachable."""
    try:
        with get_pool().connection(timeout=5) as conn:
            version = conn.execute("SHOW server_version").fetchone()["server_version"]
        return {"status": "connected", "detail": f"PostgreSQL {version} on Aiven"}
    except DatabaseNotConfigured as e:
        return {"status": "error", "detail": str(e)}
    except Exception as e:
        return {"status": "error", "detail": f"{type(e).__name__}: {e}"}


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None

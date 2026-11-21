"""
PostgreSQL connection pool.

Opening a new connection to Aiven (over the internet, with TLS) takes a moment,
so we keep a small pool of open connections and reuse them for every request.
Rows come back as dictionaries, e.g. {"id": 1, "name": "boAt Airdopes 141"}.
"""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL, is_configured

_pool = None


class DatabaseNotConfigured(RuntimeError):
    pass


def get_pool() -> ConnectionPool:
    global _pool
    if not is_configured(DATABASE_URL):
        raise DatabaseNotConfigured("DATABASE_URL is not filled in backend/.env")
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=5,             # Aiven's free plan allows a limited number of connections
            timeout=10,             # seconds to wait for a free connection
            kwargs={"row_factory": dict_row},
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

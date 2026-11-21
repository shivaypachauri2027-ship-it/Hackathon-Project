"""
InstaStock API (FastAPI).

Run from the backend/ folder (virtual environment active):
    python -m uvicorn app.main:app --reload --port 8000

Interactive API docs (great to show judges): http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

import psycopg
from psycopg.errors import UndefinedTable
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout

from . import catalog, db
from .config import CORS_ORIGINS, DEFAULT_CITY


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: open the database pool early so the first page load is fast.
    try:
        db.get_pool()
    except Exception as e:  # the API still starts; /api/health shows the problem
        print(f"WARNING: database not ready: {e}")
    yield
    # Shutdown: close database connections cleanly.
    db.close_pool()


app = FastAPI(
    title="InstaStock API",
    version="0.2.0",
    description="Event-driven online store: PostgreSQL + Kafka + OpenSearch",
    lifespan=lifespan,
)

# Lets the React dev server (http://localhost:5173) call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# If the database is unreachable, answer with a clear message instead of a crash.
@app.exception_handler(psycopg.OperationalError)
@app.exception_handler(PoolTimeout)
@app.exception_handler(db.DatabaseNotConfigured)
async def database_unavailable(request: Request, exc: Exception):
    return JSONResponse(
        status_code=503,
        content={"detail": f"Database unavailable: {exc}. Check DATABASE_URL in backend/.env "
                           "and that the Aiven PostgreSQL service is running."},
    )


@app.exception_handler(UndefinedTable)
async def tables_missing(request: Request, exc: Exception):
    return JSONResponse(
        status_code=503,
        content={"detail": "Database tables are missing. Run:  python scripts/seed_db.py"},
    )


def _check_city(city: str) -> str:
    cities = catalog.list_cities()
    if city not in cities:
        raise HTTPException(400, f"Unknown city '{city}'. Choose one of: {', '.join(cities)}")
    return city


@app.get("/api/health")
def health():
    """The footer of the website shows these statuses."""
    return {
        "status": "ok",
        "phase": 2,
        "catalog_source": catalog.SOURCE,
        "services": {
            "postgres": db.ping(),
            "kafka": {"status": "pending", "detail": "Connected in Phase 4"},
            "opensearch": {"status": "pending", "detail": "Connected in Phase 5"},
        },
    }


@app.get("/api/meta")
def meta():
    """Everything the filter sidebar needs: categories (with counts) and cities."""
    return {"categories": catalog.list_categories(), "cities": catalog.list_cities()}


@app.get("/api/products")
def list_products(
    q: str | None = None,
    category: str | None = None,
    city: str = DEFAULT_CITY,
    min_price: int | None = None,
    max_price: int | None = None,
    in_stock: bool = False,
    sort: str = "relevance",
):
    _check_city(city)
    if sort not in catalog.SORTS:
        raise HTTPException(400, f"Unknown sort '{sort}'")
    return catalog.list_products(
        q=q.strip() if q else None,
        category=category or None,
        city=city,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        sort=sort,
    )


@app.get("/api/products/{product_id}")
def get_product(product_id: int, city: str = DEFAULT_CITY):
    _check_city(city)
    product = catalog.get_product(product_id, city)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product

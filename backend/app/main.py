"""
InstaStock API (FastAPI).

Run from the backend/ folder (virtual environment active):
    python -m uvicorn app.main:app --reload --port 8000

Interactive API docs (great to show judges): http://localhost:8000/docs
"""
import re
from contextlib import asynccontextmanager

import psycopg
from psycopg.errors import UndefinedTable
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, Field, field_validator

from . import admin, catalog, db, events, orders, search
from .config import CORS_ORIGINS, DEFAULT_CITY


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: open the database pool early so the first page load is fast.
    try:
        db.get_pool()
    except Exception as e:  # the API still starts; /api/health shows the problem
        print(f"WARNING: database not ready: {e}")
    # Start the background thread that sends outbox events to Kafka (Phase 4)
    events.start_publisher()
    yield
    # Shutdown: stop the publisher and close database connections cleanly.
    events.stop_publisher()
    db.close_pool()


app = FastAPI(
    title="InstaStock API",
    version="0.6.0",
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


@app.exception_handler(orders.OrderError)
async def order_problem(request: Request, exc: orders.OrderError):
    # e.g. 409 "Not enough stock" with the list of items that ran out
    return JSONResponse(status_code=exc.status, content={"detail": exc.message, "problems": exc.problems})


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
        "phase": 6,
        "catalog_source": catalog.SOURCE,
        "services": {
            "postgres": db.ping(),
            "kafka": events.health(),
            "opensearch": search.health(),
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


# ------------------------------------------------------------------ orders (Phase 3)

class CartItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=orders.MAX_QTY_PER_ITEM)


class Customer(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    phone: str
    address: str = Field(min_length=10, max_length=300)

    @field_validator("phone")
    @classmethod
    def indian_mobile(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)[-10:]          # accepts "+91 98765 43210"
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise ValueError("enter a 10-digit Indian mobile number")
        return digits


class OrderRequest(BaseModel):
    city: str
    customer: Customer
    items: list[CartItem] = Field(min_length=1, max_length=20)


@app.post("/api/orders", status_code=201)
def create_order(req: OrderRequest):
    """Checkout. Reserves stock atomically; returns 409 if anything ran out."""
    _check_city(req.city)
    return orders.place_order(
        req.customer.model_dump(), req.city, [item.model_dump() for item in req.items]
    )


@app.get("/api/orders")
def list_recent_orders(limit: int = 20):
    return orders.recent_orders(min(max(limit, 1), 100))


@app.get("/api/orders/{order_number}")
def get_order(order_number: str):
    order = orders.get_order(order_number.upper())
    if order is None:
        raise HTTPException(404, "Order not found")
    return order


# ------------------------------------------------------------------ live events (Phase 4)

@app.get("/api/events")
def live_events(limit: int = 25):
    """What was sent to Kafka (outbox) and what the consumers did (event_log)."""
    data = events.recent_activity(min(max(limit, 1), 100))
    data["orders"] = orders.recent_orders(10)
    return data


# ------------------------------------------------------------------ demo tools (Phase 6)
# No login: hackathon demo only. In a real store these sit behind a staff login.

class StockChange(BaseModel):
    product_id: int
    city: str
    add: int | None = Field(default=None, ge=1, le=100)
    set_available: int | None = Field(default=None, ge=0, le=100)


@app.exception_handler(admin.StockError)
async def stock_problem(request: Request, exc: admin.StockError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.post("/api/admin/stock")
def change_stock(req: StockChange):
    """Restock (add) or set exactly N available (flash sale). Publishes STOCK_CHANGED."""
    _check_city(req.city)
    return admin.change_stock(req.product_id, req.city, add=req.add, set_available=req.set_available)


@app.get("/api/admin/sync-status/{product_id}")
def sync_status(product_id: int, city: str = DEFAULT_CITY):
    """Stock in PostgreSQL (truth) vs OpenSearch (search copy), for the sync monitor."""
    _check_city(city)
    return admin.sync_status(product_id, city)

"""
InstaStock API (FastAPI).

Run from the backend/ folder:
    uvicorn app.main:app --reload --port 8000

Interactive API docs (great to show judges): http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import catalog
from .config import CORS_ORIGINS, DEFAULT_CITY

app = FastAPI(
    title="InstaStock API",
    version="0.1.0",
    description="Event-driven online store: PostgreSQL + Kafka + OpenSearch",
)

# Lets the React dev server (http://localhost:5173) call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_city(city: str) -> str:
    if city not in catalog.list_cities():
        raise HTTPException(400, f"Unknown city '{city}'. Choose one of: {', '.join(catalog.list_cities())}")
    return city


@app.get("/api/health")
def health():
    """The footer of the website shows these statuses. Later phases fill in real checks."""
    return {
        "status": "ok",
        "phase": 1,
        "catalog_source": catalog.SOURCE,
        "services": {
            "postgres": {"status": "pending", "detail": "Connected in Phase 2"},
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

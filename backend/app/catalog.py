"""
Product catalog — PHASE 1 VERSION.

Right now products come from data/products.json so the app works before any cloud
service is connected. Search here is a plain "contains" match (NOT typo tolerant).

Phase 2 replaces these functions with PostgreSQL queries.
Phase 5 sends search to OpenSearch (typo tolerant).
The function names and the shape of the data they return stay the same,
so the frontend never has to change.
"""
import json
from functools import lru_cache

from .config import BACKEND_DIR

SOURCE = "json-file"
SEARCH_MODE = "exact words only (Phase 1 placeholder)"
SORTS = {"relevance", "price_asc", "price_desc", "rating", "discount"}


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(BACKEND_DIR / "data" / "products.json", encoding="utf-8") as f:
        return json.load(f)


def list_cities() -> list[str]:
    return _load()["cities"]


def _to_card(p: dict, city: str) -> dict:
    """The product shape the frontend expects (same shape in every phase)."""
    stock = p["stock"]
    mrp, price = p["mrp"], p["price"]
    return {
        "id": p["id"],
        "sku": p["sku"],
        "name": p["name"],
        "brand": p["brand"],
        "category": p["category"],
        "price": price,
        "mrp": mrp,
        "discount_pct": round((mrp - price) * 100 / mrp) if mrp > price else 0,
        "rating": p["rating"],
        "rating_count": p["rating_count"],
        "image_url": p["image_url"],
        "description": p["description"],
        "tags": p["tags"],
        "city": city,
        "stock_in_city": stock.get(city, 0),
        "total_stock": sum(stock.values()),
        "stock_by_city": stock,
    }


def _matches(p: dict, words: list[str]) -> bool:
    text = " ".join([p["name"], p["brand"], p["category"], " ".join(p["tags"])]).lower()
    return all(w in text for w in words)


def list_products(q=None, category=None, city="Bengaluru", min_price=None,
                  max_price=None, in_stock=False, sort="relevance") -> dict:
    items = _load()["products"]

    if q:
        words = q.lower().split()
        items = [p for p in items if _matches(p, words)]
    if category:
        items = [p for p in items if p["category"] == category]
    if min_price is not None:
        items = [p for p in items if p["price"] >= min_price]
    if max_price is not None:
        items = [p for p in items if p["price"] <= max_price]

    cards = [_to_card(p, city) for p in items]
    if in_stock:
        cards = [c for c in cards if c["stock_in_city"] > 0]

    if sort == "price_asc":
        cards.sort(key=lambda c: c["price"])
    elif sort == "price_desc":
        cards.sort(key=lambda c: c["price"], reverse=True)
    elif sort == "rating":
        cards.sort(key=lambda c: (c["rating"], c["rating_count"]), reverse=True)
    elif sort == "discount":
        cards.sort(key=lambda c: c["discount_pct"], reverse=True)

    return {
        "items": cards,
        "total": len(cards),
        "city": city,
        "source": SOURCE,
        "search_mode": SEARCH_MODE,
    }


def get_product(product_id: int, city: str):
    for p in _load()["products"]:
        if p["id"] == product_id:
            return _to_card(p, city)
    return None


def list_categories() -> list[dict]:
    counts = {}
    for p in _load()["products"]:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    return [{"name": name, "count": counts.get(name, 0)} for name in _load()["categories"]]

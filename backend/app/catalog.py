"""
Product catalog — PHASE 5 VERSION.

Browsing and searching use OPENSEARCH (typo-tolerant, fast filters).
If OpenSearch is switched off or unreachable, we fall back to PostgreSQL
(exact words only) and the website says so. Product details and checkout
always read PostgreSQL, the source of truth.
"""
from . import db, search

SOURCE = "opensearch" if search.is_enabled() else "postgres"
SEARCH_MODE = "exact words, PostgreSQL ILIKE"

# Whitelist of ORDER BY clauses: user input never goes into SQL directly
SORTS = {
    "relevance": "p.id",
    "price_asc": "p.price ASC, p.id",
    "price_desc": "p.price DESC, p.id",
    "rating": "p.rating DESC, p.rating_count DESC",
    "discount": "(p.mrp - p.price)::float / p.mrp DESC, p.id",
}

# One query returns each product with:
#   stock_in_city  = available units in the shopper's city (on_hand - reserved)
#   total_stock    = available units across all cities
#   stock_by_city  = {"Bengaluru": 3, "Mumbai": 0, ...}
PRODUCT_SELECT = """
    SELECT p.id, p.sku, p.name, p.brand, p.category, p.price, p.mrp,
           p.rating, p.rating_count, p.image_url, p.description, p.tags,
           COALESCE(i.on_hand - i.reserved, 0) AS stock_in_city,
           s.total_stock, s.stock_by_city
    FROM products p
    LEFT JOIN inventory i ON i.product_id = p.id AND i.city = %(city)s
    CROSS JOIN LATERAL (
        SELECT COALESCE(SUM(inv.on_hand - inv.reserved), 0)::int AS total_stock,
               COALESCE(json_object_agg(inv.city, inv.on_hand - inv.reserved ORDER BY c.sort_order),
                        '{}'::json) AS stock_by_city
        FROM inventory inv
        JOIN cities c ON c.name = inv.city
        WHERE inv.product_id = p.id
    ) s
"""


def _to_card(row: dict, city: str) -> dict:
    """Same product shape as Phase 1 (the frontend depends on it)."""
    mrp, price = row["mrp"], row["price"]
    return {
        "id": row["id"],
        "sku": row["sku"],
        "name": row["name"],
        "brand": row["brand"],
        "category": row["category"],
        "price": price,
        "mrp": mrp,
        "discount_pct": round((mrp - price) * 100 / mrp) if mrp > price else 0,
        "rating": float(row["rating"]),
        "rating_count": row["rating_count"],
        "image_url": row["image_url"],
        "description": row["description"],
        "tags": row["tags"],
        "city": city,
        "stock_in_city": row["stock_in_city"],
        "total_stock": row["total_stock"],
        "stock_by_city": row["stock_by_city"],
    }


def _like(word: str) -> str:
    """Wrap a search word for ILIKE and escape the wildcard characters % and _."""
    word = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{word}%"


_cities_cache: list[str] = []


def list_cities() -> list[str]:
    # Cities never change while the app runs, so we read them once (only cache a non-empty list)
    if not _cities_cache:
        with db.connection() as conn:
            rows = conn.execute("SELECT name FROM cities ORDER BY sort_order").fetchall()
        _cities_cache.extend(r["name"] for r in rows)
    return _cities_cache


def list_categories() -> list[dict]:
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT category AS name, COUNT(*)::int AS count FROM products "
            "GROUP BY category ORDER BY MIN(id)"
        ).fetchall()
    return rows


def list_products(q=None, category=None, city="Bengaluru", min_price=None,
                  max_price=None, in_stock=False, sort="relevance") -> dict:
    args = dict(q=q, category=category, city=city, min_price=min_price,
                max_price=max_price, in_stock=in_stock, sort=sort)
    if search.is_enabled():
        try:
            return search.search_products(**args)
        except Exception as e:
            result = _list_products_postgres(**args)
            result["search_mode"] = f"PostgreSQL FALLBACK, exact words only (OpenSearch error: {type(e).__name__})"
            return result
    result = _list_products_postgres(**args)
    result["search_mode"] = "PostgreSQL FALLBACK, exact words only (OpenSearch is switched off)"
    return result


def _list_products_postgres(q=None, category=None, city="Bengaluru", min_price=None,
                            max_price=None, in_stock=False, sort="relevance") -> dict:
    where, params = [], {"city": city}

    if q:
        # Every word must appear in the name, brand, category or tags
        for n, word in enumerate(q.lower().split()[:8]):
            key = f"w{n}"
            params[key] = _like(word)
            where.append(
                f"(p.name ILIKE %({key})s OR p.brand ILIKE %({key})s OR p.category ILIKE %({key})s "
                f"OR array_to_string(p.tags, ' ') ILIKE %({key})s)"
            )
    if category:
        where.append("p.category = %(category)s")
        params["category"] = category
    if min_price is not None:
        where.append("p.price >= %(min_price)s")
        params["min_price"] = min_price
    if max_price is not None:
        where.append("p.price <= %(max_price)s")
        params["max_price"] = max_price
    if in_stock:
        where.append("COALESCE(i.on_hand - i.reserved, 0) > 0")

    sql = PRODUCT_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + SORTS.get(sort, SORTS["relevance"])

    with db.connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    items = [_to_card(r, city) for r in rows]
    return {
        "items": items,
        "total": len(items),
        "city": city,
        "source": "postgres",
        "search_mode": SEARCH_MODE,
    }


def get_product(product_id: int, city: str):
    with db.connection() as conn:
        row = conn.execute(PRODUCT_SELECT + " WHERE p.id = %(id)s", {"city": city, "id": product_id}).fetchone()
    return _to_card(row, city) if row else None

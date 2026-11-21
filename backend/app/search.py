"""
OpenSearch — fast, TYPO-TOLERANT product search with filters.

PostgreSQL stays the source of truth. OpenSearch keeps a COPY of every product
(with its stock per city) that is optimised for searching:
  * fuzzy matching: "bluetoth" finds "Bluetooth", "samsng" finds "Samsung"
  * search-as-you-type: "noise ear" finds "Noise ... Earbuds"
  * filters: category, price range, "in stock in my city"

How the copy stays up to date (event-driven):
  order placed -> Kafka order-events -> inventory-worker updates stock in PostgreSQL
  -> Kafka inventory-events -> search-sync worker calls sync_products() below
  -> those products are re-indexed here, usually within a second or two.
"""
import time

from . import db
from .config import OPENSEARCH_ENABLED, OPENSEARCH_INDEX, OPENSEARCH_URL, is_configured

_client = None

# How the index is structured. "search_text" collects name, brand, category,
# tags and description into one field, so a query like "noise earbuds" can match
# the brand in one field and the product type in another.
INDEX_BODY = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "id": {"type": "integer"},
            "sku": {"type": "keyword"},
            "name": {"type": "text", "copy_to": "search_text"},
            "brand": {"type": "text", "copy_to": "search_text", "fields": {"raw": {"type": "keyword"}}},
            "category": {"type": "keyword", "copy_to": "search_text"},
            "tags": {"type": "text", "copy_to": "search_text"},
            "description": {"type": "text", "copy_to": "search_text"},
            "search_text": {"type": "text"},
            "price": {"type": "integer"},
            "mrp": {"type": "integer"},
            "discount_pct": {"type": "integer"},
            "rating": {"type": "float"},
            "rating_count": {"type": "integer"},
            "image_url": {"type": "keyword", "index": False},
            "stock_by_city": {"type": "object"},
            "in_stock_cities": {"type": "keyword"},
            "total_stock": {"type": "integer"},
            "indexed_at": {"type": "date"},
        }
    },
}

SORTS = {
    "relevance": [{"_score": "desc"}, {"id": "asc"}],
    "price_asc": [{"price": "asc"}, {"id": "asc"}],
    "price_desc": [{"price": "desc"}, {"id": "asc"}],
    "rating": [{"rating": "desc"}, {"rating_count": "desc"}],
    "discount": [{"discount_pct": "desc"}, {"id": "asc"}],
}


def is_enabled() -> bool:
    return OPENSEARCH_ENABLED and is_configured(OPENSEARCH_URL)


def client():
    global _client
    if _client is None:
        from opensearchpy import OpenSearch

        _client = OpenSearch(
            hosts=[OPENSEARCH_URL],
            use_ssl=True,
            verify_certs=True,
            timeout=10,
            max_retries=2,
            retry_on_timeout=True,
        )
    return _client


# ------------------------------------------------------------------ indexing

DOCS_SQL = """
    SELECT p.id, p.sku, p.name, p.brand, p.category, p.price, p.mrp, p.rating, p.rating_count,
           p.image_url, p.description, p.tags,
           s.total_stock, s.stock_by_city, s.in_stock_cities
      FROM products p
     CROSS JOIN LATERAL (
        SELECT COALESCE(SUM(i.on_hand - i.reserved), 0)::int AS total_stock,
               COALESCE(json_object_agg(i.city, i.on_hand - i.reserved ORDER BY c.sort_order), '{}'::json)
                   AS stock_by_city,
               COALESCE(array_agg(i.city ORDER BY c.sort_order) FILTER (WHERE i.on_hand - i.reserved > 0),
                        '{}') AS in_stock_cities
          FROM inventory i JOIN cities c ON c.name = i.city
         WHERE i.product_id = p.id
     ) s
"""


def _doc(row: dict) -> dict:
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
        "stock_by_city": row["stock_by_city"],
        "in_stock_cities": row["in_stock_cities"],
        "total_stock": row["total_stock"],
        "indexed_at": int(time.time() * 1000),
    }


def load_docs(product_ids=None) -> list[dict]:
    """Reads products + current stock from PostgreSQL (the source of truth)."""
    with db.connection() as conn:
        if product_ids is None:
            rows = conn.execute(DOCS_SQL + " ORDER BY p.id").fetchall()
        else:
            rows = conn.execute(DOCS_SQL + " WHERE p.id = ANY(%s) ORDER BY p.id", (list(product_ids),)).fetchall()
    return [_doc(r) for r in rows]


def index_docs(docs: list[dict]) -> int:
    from opensearchpy import helpers

    actions = [{"_op_type": "index", "_index": OPENSEARCH_INDEX, "_id": d["id"], "_source": d} for d in docs]
    if not actions:
        return 0
    # refresh=True makes the new stock visible to the very next search
    success, _ = helpers.bulk(client(), actions, refresh=True)
    return success


def sync_products(product_ids) -> int:
    """Called by the search-sync Kafka consumer: re-index the products whose stock changed."""
    return index_docs(load_docs(product_ids))


def create_index(recreate: bool = False):
    c = client()
    if c.indices.exists(index=OPENSEARCH_INDEX):
        if not recreate:
            return False
        c.indices.delete(index=OPENSEARCH_INDEX)
    c.indices.create(index=OPENSEARCH_INDEX, body=INDEX_BODY)
    return True


# ------------------------------------------------------------------ searching

def _query(q, city, min_price, max_price, in_stock) -> dict:
    """Text + price + availability. (The category filter is applied separately as a
    post_filter, so the category chips can still show counts for every category.)"""
    filters = []
    if min_price is not None or max_price is not None:
        price = {}
        if min_price is not None:
            price["gte"] = min_price
        if max_price is not None:
            price["lte"] = max_price
        filters.append({"range": {"price": price}})
    if in_stock:
        filters.append({"term": {"in_stock_cities": city}})

    if not q:
        return {"bool": {"filter": filters}} if filters else {"match_all": {}}

    return {
        "bool": {
            "must": [{
                "bool": {
                    "should": [
                        # 1) every word must match, allowing typos (1-2 wrong letters)
                        {"match": {"search_text": {"query": q, "operator": "and",
                                                   "fuzziness": "AUTO", "prefix_length": 1}}},
                        # 2) search-as-you-type: the last word may be unfinished ("noise ear")
                        {"match_bool_prefix": {"search_text": {"query": q, "operator": "and"}}},
                    ],
                    "minimum_should_match": 1,
                }
            }],
            # Ranking boosts: matches in the product name and brand come first
            "should": [
                {"match_phrase": {"name": {"query": q, "boost": 6}}},
                {"match": {"name": {"query": q, "fuzziness": "AUTO", "boost": 3}}},
                {"match": {"brand": {"query": q, "fuzziness": "AUTO", "boost": 2}}},
            ],
            "filter": filters,
        }
    }


def _did_you_mean(q: str, suggest: dict) -> str | None:
    """Builds 'bluetooth speaker' from the suggestions for 'bluetoth speaker'."""
    entries = (suggest or {}).get("spelling") or []
    words, changed = [], False
    for entry in entries:
        options = entry.get("options") or []
        if options:
            words.append(options[0]["text"])
            changed = True
        else:
            words.append(entry["text"])
    return " ".join(words) if changed and words else None


def search_products(q=None, category=None, city="Bengaluru", min_price=None,
                    max_price=None, in_stock=False, sort="relevance") -> dict:
    body = {
        "size": 100,
        "query": _query(q, city, min_price, max_price, in_stock),
        "sort": SORTS.get(sort, SORTS["relevance"]) if q or sort != "relevance" else [{"id": "asc"}],
        # Counts per category for the chips (an OpenSearch aggregation), computed
        # BEFORE the category filter so every chip shows how many matches it has
        "aggs": {"categories": {"terms": {"field": "category", "size": 20}}},
    }
    if category:
        body["post_filter"] = {"term": {"category": category}}
    if q:
        body["suggest"] = {"spelling": {"text": q, "term": {"field": "search_text", "suggest_mode": "missing"}}}

    res = client().search(index=OPENSEARCH_INDEX, body=body)

    items = []
    for hit in res["hits"]["hits"]:
        d = hit["_source"]
        stock = d.get("stock_by_city") or {}
        items.append({
            "id": d["id"], "sku": d["sku"], "name": d["name"], "brand": d["brand"], "category": d["category"],
            "price": d["price"], "mrp": d["mrp"], "discount_pct": d["discount_pct"],
            "rating": d["rating"], "rating_count": d["rating_count"], "image_url": d["image_url"],
            "description": d["description"], "tags": d["tags"],
            "city": city, "stock_in_city": stock.get(city, 0),
            "total_stock": d["total_stock"], "stock_by_city": stock,
        })

    return {
        "items": items,
        "total": len(items),
        "city": city,
        "source": "opensearch",
        "search_mode": f"typo-tolerant search in {res.get('took', 0)} ms" if q else f"{res.get('took', 0)} ms",
        "did_you_mean": _did_you_mean(q, res.get("suggest")) if q else None,
        "facets": {
            "categories": [
                {"name": b["key"], "count": b["doc_count"]}
                for b in res.get("aggregations", {}).get("categories", {}).get("buckets", [])
            ]
        },
    }


def get_stock(product_id: int, city: str) -> int:
    """What the SEARCH COPY currently says is available (for the sync monitor)."""
    doc = client().get(index=OPENSEARCH_INDEX, id=product_id)["_source"]
    return (doc.get("stock_by_city") or {}).get(city, 0)


def health() -> dict:
    if not OPENSEARCH_ENABLED:
        return {"status": "pending", "detail": "OPENSEARCH_ENABLED=false: search uses the PostgreSQL fallback"}
    if not is_configured(OPENSEARCH_URL):
        return {"status": "pending", "detail": "Fill OPENSEARCH_URL in backend/.env"}
    try:
        c = client()
        if not c.indices.exists(index=OPENSEARCH_INDEX):
            return {"status": "error", "detail": "Index missing. Run: python scripts/index_products.py"}
        count = c.count(index=OPENSEARCH_INDEX)["count"]
        return {"status": "connected", "detail": f"{count} products indexed in '{OPENSEARCH_INDEX}'"}
    except Exception as e:
        return {"status": "error", "detail": f"{type(e).__name__}: {e}"}

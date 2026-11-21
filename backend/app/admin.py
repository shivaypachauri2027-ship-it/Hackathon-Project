"""
Demo / store-manager tools (Phase 6).

  change_stock()  restock a product in a city, or set exactly N available
                  (used by the Flash sale demo). Like an order, it writes a
                  STOCK_CHANGED event to the outbox in the SAME transaction,
                  so Kafka's search-sync worker updates OpenSearch.
  sync_status()   the same product's stock in PostgreSQL (truth) and in
                  OpenSearch (search copy), so the demo can show them converge.

These endpoints have no login because this is a hackathon demo. In a real
store they would sit behind a staff login.
"""
from psycopg.types.json import Jsonb

from . import catalog, db, events, search
from .config import KAFKA_INVENTORY_TOPIC


class StockError(Exception):
    pass


def change_stock(product_id: int, city: str, add: int | None = None, set_available: int | None = None) -> dict:
    if (add is None) == (set_available is None):
        raise StockError("Send exactly one of 'add' or 'set_available'.")

    reason = "RESTOCK" if add is not None else "FLASH_SALE_SETUP"
    with db.connection() as conn:  # ONE transaction: stock change + its event
        if add is not None:
            row = conn.execute(
                """UPDATE inventory SET on_hand = on_hand + %s, updated_at = now()
                    WHERE product_id = %s AND city = %s
                RETURNING on_hand - reserved AS available""",
                (add, product_id, city),
            ).fetchone()
        else:
            # available = on_hand - reserved, so on_hand = reserved + wanted
            row = conn.execute(
                """UPDATE inventory SET on_hand = reserved + %s, updated_at = now()
                    WHERE product_id = %s AND city = %s
                RETURNING on_hand - reserved AS available""",
                (set_available, product_id, city),
            ).fetchone()
        if row is None:
            raise StockError(f"No stock row for product {product_id} in {city}.")

        conn.execute(
            "INSERT INTO outbox_events (topic, event_type, event_key, payload) VALUES (%s, 'STOCK_CHANGED', %s, %s)",
            (KAFKA_INVENTORY_TOPIC, reason, Jsonb({
                "event_type": "STOCK_CHANGED",
                "reason": reason,
                "order_number": None,
                "city": city,
                "product_ids": [product_id],
            })),
        )
    events.notify()  # send the event to Kafka right away
    return {"product_id": product_id, "city": city, "available": row["available"], "reason": reason}


def sync_status(product_id: int, city: str) -> dict:
    product = catalog.get_product(product_id, city)
    if product is None:
        raise StockError("Product not found")
    in_search = None
    if search.is_enabled():
        try:
            in_search = search.get_stock(product_id, city)
        except Exception:
            in_search = None
    return {
        "product_id": product_id,
        "name": product["name"],
        "city": city,
        "postgres": product["stock_in_city"],
        "search_enabled": search.is_enabled(),
        "opensearch": in_search,
        "in_sync": in_search is not None and in_search == product["stock_in_city"],
    }

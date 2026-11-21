"""
Checkout — turns a cart into an order WITHOUT EVER OVERSELLING.

How overselling is prevented (the key idea to explain to judges):
  For every item we run ONE atomic SQL statement:

      UPDATE inventory
         SET reserved = reserved + <qty>
       WHERE product_id = <id> AND city = <city>
         AND on_hand - reserved >= <qty>      <-- only if enough is available

  PostgreSQL locks the stock row while it updates it. If two shoppers try to
  buy the last unit at the same moment, the second UPDATE waits, then sees
  that nothing is left and changes 0 rows. We treat "0 rows changed" as
  "out of stock" and roll back the whole order. One buyer wins, never two.

Everything (reserve stock, save order, save the Kafka event in the outbox)
happens in ONE transaction: either all of it is saved, or none of it.
"""
import secrets
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from . import db, events
from .config import KAFKA_ORDER_TOPIC

MAX_QTY_PER_ITEM = 10


class OrderError(Exception):
    """A problem the shopper can fix (shown in the UI)."""

    def __init__(self, message: str, status: int = 400, problems: list | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.problems = problems or []


def _new_order_number() -> str:
    return "IS-" + secrets.token_hex(3).upper()      # e.g. IS-7F3A2C


def _mask_phone(phone: str) -> str:
    return phone[:2] + "*" * 6 + phone[-2:] if len(phone) == 10 else phone


def place_order(customer: dict, city: str, items: list[dict]) -> dict:
    # Merge duplicate lines (same product twice) and validate quantities
    wanted: dict[int, int] = {}
    for item in items:
        wanted[item["product_id"]] = wanted.get(item["product_id"], 0) + item["quantity"]
    for pid, qty in wanted.items():
        if qty > MAX_QTY_PER_ITEM:
            raise OrderError(f"You can buy at most {MAX_QTY_PER_ITEM} units of one product.")

    # Always lock rows in the same order (by product id) so two orders can't deadlock
    product_ids = sorted(wanted)
    order_number = _new_order_number()

    # ---- ONE TRANSACTION starts here (commit at the end, rollback on any error) ----
    with db.connection() as conn:
        products = {
            row["id"]: row
            for row in conn.execute(
                "SELECT id, name, price FROM products WHERE id = ANY(%s)", (product_ids,)
            ).fetchall()
        }
        unknown = [pid for pid in product_ids if pid not in products]
        if unknown:
            raise OrderError(f"Unknown product id(s): {unknown}", status=404)

        problems = []
        for pid in product_ids:
            qty = wanted[pid]
            reserved = conn.execute(
                """
                UPDATE inventory
                   SET reserved = reserved + %(qty)s, updated_at = now()
                 WHERE product_id = %(pid)s AND city = %(city)s
                   AND on_hand - reserved >= %(qty)s
                RETURNING on_hand - reserved AS available_after
                """,
                {"qty": qty, "pid": pid, "city": city},
            ).fetchone()

            if reserved is None:  # 0 rows changed => not enough stock
                row = conn.execute(
                    "SELECT on_hand - reserved AS available FROM inventory WHERE product_id = %s AND city = %s",
                    (pid, city),
                ).fetchone()
                problems.append({
                    "product_id": pid,
                    "name": products[pid]["name"],
                    "requested": qty,
                    "available": row["available"] if row else 0,
                })

        if problems:
            # Raising inside the `with` block ROLLS BACK every reservation made above
            names = ", ".join(p["name"] for p in problems)
            raise OrderError(f"Not enough stock in {city} for: {names}", status=409, problems=problems)

        total = sum(products[pid]["price"] * wanted[pid] for pid in product_ids)
        order = conn.execute(
            """
            INSERT INTO orders (order_number, customer_name, phone, address, city, total_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (order_number, customer["name"].strip(), customer["phone"], customer["address"].strip(), city, total),
        ).fetchone()

        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
                [(order["id"], pid, wanted[pid], products[pid]["price"]) for pid in product_ids],
            )

        # The event for Kafka is saved in the SAME transaction (transactional outbox).
        # Phase 4's publisher reads this table and sends it to the 'order-events' topic.
        event = {
            "event_type": "ORDER_PLACED",
            "order_id": order["id"],
            "order_number": order_number,
            "city": city,
            "items": [{"product_id": pid, "quantity": wanted[pid]} for pid in product_ids],
            "total_amount": total,
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }
        conn.execute(
            "INSERT INTO outbox_events (topic, event_type, event_key, payload) VALUES (%s, %s, %s, %s)",
            (KAFKA_ORDER_TOPIC, "ORDER_PLACED", order_number, Jsonb(event)),
        )
    # ---- COMMIT happened here ----

    events.notify()  # wake the outbox publisher so the event reaches Kafka right away
    return get_order(order_number)


ORDER_QUERY = """
    SELECT o.id, o.order_number, o.customer_name, o.phone, o.address, o.city,
           o.total_amount, o.payment_method, o.status, o.created_at, o.confirmed_at,
           (SELECT published_at FROM outbox_events
             WHERE event_key = o.order_number AND event_type = 'ORDER_PLACED'
             ORDER BY id LIMIT 1) AS published_at,
           (SELECT row_to_json(e) FROM (
                SELECT processed_at, kafka_partition, kafka_offset, detail FROM event_log
                 WHERE consumer = 'inventory-worker' AND event_key = o.order_number
                 ORDER BY id LIMIT 1) e) AS confirm_log,
           (SELECT row_to_json(e) FROM (
                SELECT processed_at, kafka_partition, kafka_offset, detail FROM event_log
                 WHERE consumer = 'search-sync' AND event_key = o.order_number
                 ORDER BY id LIMIT 1) e) AS index_log
      FROM orders o
     WHERE o.order_number = %s
"""


def _journey(o: dict) -> list[dict]:
    """The 4 steps an order goes through. The confirmation page shows them live."""
    confirm, index = o["confirm_log"] or {}, o["index_log"] or {}

    def kafka_detail(log):
        if log.get("kafka_partition") is None:
            return log.get("detail") or ""
        return f"partition {log['kafka_partition']}, offset {log['kafka_offset']}"

    return [
        {"key": "reserved", "label": "Stock reserved in PostgreSQL", "done": True,
         "at": o["created_at"], "detail": "Units are held for you; nobody else can buy them."},
        {"key": "published", "label": "Order event sent to Kafka", "done": o["published_at"] is not None,
         "at": o["published_at"],
         "detail": "Topic order-events" if o["published_at"] else "Waiting for the event publisher"},
        {"key": "confirmed", "label": "Inventory worker confirmed the order", "done": o["status"] == "CONFIRMED",
         "at": o["confirmed_at"],
         "detail": kafka_detail(confirm) if confirm else "Waiting for the Kafka consumer"},
        {"key": "indexed", "label": "Search results updated in OpenSearch", "done": bool(index),
         "at": index.get("processed_at"),
         "detail": kafka_detail(index) if index else "Waiting for the search sync worker"},
    ]


def get_order(order_number: str):
    with db.connection() as conn:
        o = conn.execute(ORDER_QUERY, (order_number,)).fetchone()
        if o is None:
            return None
        items = conn.execute(
            """
            SELECT oi.product_id, p.name, p.brand, p.image_url, oi.quantity, oi.unit_price,
                   oi.quantity * oi.unit_price AS line_total
              FROM order_items oi JOIN products p ON p.id = oi.product_id
             WHERE oi.order_id = %s ORDER BY p.name
            """,
            (o["id"],),
        ).fetchall()

    return {
        "order_number": o["order_number"],
        "status": o["status"],
        "city": o["city"],
        "customer_name": o["customer_name"],
        "phone": _mask_phone(o["phone"]),
        "address": o["address"],
        "payment_method": o["payment_method"],
        "total_amount": o["total_amount"],
        "created_at": o["created_at"],
        "items": items,
        "journey": _journey(o),
    }


def recent_orders(limit: int = 20) -> list[dict]:
    """Latest orders, without personal details (used by the demo pages)."""
    with db.connection() as conn:
        return conn.execute(
            """
            SELECT o.order_number, o.city, o.total_amount, o.status, o.created_at,
                   COALESCE(SUM(oi.quantity), 0)::int AS units
              FROM orders o LEFT JOIN order_items oi ON oi.order_id = o.id
             GROUP BY o.id ORDER BY o.created_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()

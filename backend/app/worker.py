"""
Kafka CONSUMERS (the "workers"). Run in its own terminal, from the backend/ folder:

    python -m app.worker

Two consumer groups run here, each in its own thread:

  inventory-worker  reads topic order-events
                    -> confirms the order (PLACED -> CONFIRMED)
                    -> finalises stock: moves units from 'reserved' to sold
                       (on_hand - qty, reserved - qty)
                    -> records a confirmation message
                    -> publishes STOCK_CHANGED to topic inventory-events

  search-sync       reads topic inventory-events
                    -> refreshes those products in OpenSearch (Phase 5)

Both are IDEMPOTENT: if Kafka delivers the same event twice, the second copy
changes nothing (the order is already CONFIRMED, so the UPDATE matches 0 rows).
Offsets are committed only AFTER an event was processed successfully, so a crash
never loses an event: it is simply processed again.
"""
import json
import signal
import threading
import time

from psycopg.types.json import Jsonb

from . import db, events, search
from .config import KAFKA_INVENTORY_TOPIC, KAFKA_ORDER_TOPIC, kafka_client_config

_stop = threading.Event()


def _mask(phone: str) -> str:
    return phone[:2] + "******" + phone[-2:] if len(phone) == 10 else phone


# --------------------------------------------------------------- handlers

def handle_order_placed(event: dict, topic: str, partition: int, offset: int) -> str:
    if event.get("event_type") != "ORDER_PLACED":
        return f"ignored event type {event.get('event_type')}"
    order_number = event["order_number"]
    with db.connection() as conn:  # ONE transaction
        order = conn.execute(
            """UPDATE orders SET status = 'CONFIRMED', confirmed_at = now()
                WHERE order_number = %s AND status = 'PLACED'
            RETURNING id, city, phone""",
            (order_number,),
        ).fetchone()
        if order is None:
            return f"{order_number}: already confirmed or unknown, skipped (idempotent)"

        items = conn.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = %s ORDER BY product_id",
            (order["id"],),
        ).fetchall()
        for item in items:
            # The units were held in 'reserved' at checkout; now they leave the store
            conn.execute(
                """UPDATE inventory
                      SET on_hand = on_hand - %(q)s, reserved = reserved - %(q)s, updated_at = now()
                    WHERE product_id = %(p)s AND city = %(c)s""",
                {"q": item["quantity"], "p": item["product_id"], "c": order["city"]},
            )

        units = sum(i["quantity"] for i in items)
        detail = (f"Order confirmed, {units} unit{'s' if units != 1 else ''} moved from reserved to sold, "
                  f"confirmation SMS queued to {_mask(order['phone'])}")
        conn.execute(
            """INSERT INTO event_log (consumer, topic, event_type, event_key, kafka_partition, kafka_offset, detail)
               VALUES ('inventory-worker', %s, 'ORDER_PLACED', %s, %s, %s, %s)""",
            (topic, order_number, partition, offset, detail),
        )
        # Tell everyone else (search-sync) that stock changed: saved in the outbox, same transaction
        conn.execute(
            "INSERT INTO outbox_events (topic, event_type, event_key, payload) VALUES (%s, 'STOCK_CHANGED', %s, %s)",
            (KAFKA_INVENTORY_TOPIC, order_number, Jsonb({
                "event_type": "STOCK_CHANGED",
                "reason": "ORDER_CONFIRMED",
                "order_number": order_number,
                "city": order["city"],
                "product_ids": [i["product_id"] for i in items],
            })),
        )
    events.notify()
    return f"{order_number}: CONFIRMED, {units} unit(s) in {order['city']}"


def handle_stock_changed(event: dict, topic: str, partition: int, offset: int) -> str:
    product_ids = event.get("product_ids", [])
    if not search.is_enabled():
        return f"{event.get('order_number', '-')}: OpenSearch not connected yet, skipped {len(product_ids)} product(s)"

    synced = search.sync_products(product_ids)
    with db.connection() as conn:
        conn.execute(
            """INSERT INTO event_log (consumer, topic, event_type, event_key, kafka_partition, kafka_offset, detail)
               VALUES ('search-sync', %s, %s, %s, %s, %s, %s)""",
            (topic, event.get("event_type", "STOCK_CHANGED"), event.get("order_number") or event.get("reason"),
             partition, offset, f"Re-indexed {synced} product(s) in OpenSearch"),
        )
    return f"{event.get('order_number', '-')}: re-indexed {synced} product(s) in OpenSearch"


# --------------------------------------------------------------- consumer loop

def run_consumer(name: str, topic: str, handler):
    """Reads events forever. Reconnects if Kafka drops; retries an event if processing fails."""
    from kafka import KafkaConsumer

    while not _stop.is_set():
        consumer = None
        try:
            consumer = KafkaConsumer(
                topic,
                group_id=name,                 # consumer group = this worker's name
                client_id=f"instastock-{name}",
                auto_offset_reset="earliest",  # first run: also process events sent before the worker existed
                enable_auto_commit=False,      # we commit only after processing succeeded
                **kafka_client_config(),
            )
            print(f"[{name}] connected, listening to topic '{topic}'", flush=True)

            while not _stop.is_set():
                batch = consumer.poll(timeout_ms=1000, max_records=20)
                if not batch:
                    continue
                for tp, records in batch.items():
                    for rec in records:
                        try:
                            event = json.loads(rec.value)
                        except (TypeError, ValueError):
                            print(f"[{name}] skipping unreadable message at offset {rec.offset}", flush=True)
                            continue
                        try:
                            result = handler(event, rec.topic, rec.partition, rec.offset)
                            print(f"[{name}] {rec.topic} p{rec.partition} @{rec.offset}  {result}", flush=True)
                        except Exception as e:
                            # Not committed: go back to this event and try again shortly
                            print(f"[{name}] failed at offset {rec.offset}, will retry: {type(e).__name__}: {e}", flush=True)
                            consumer.seek(tp, rec.offset)
                            time.sleep(3)
                            break
                consumer.commit()              # save our position: these events are done
        except Exception as e:
            print(f"[{name}] Kafka connection problem, reconnecting in 5 s: {type(e).__name__}: {e}", flush=True)
            _stop.wait(5)
        finally:
            if consumer is not None:
                try:
                    consumer.close()
                except Exception:
                    pass


def main():
    mode = events.kafka_mode()
    if mode != "kafka":
        print("Kafka is not configured (check KAFKA_ENABLED and KAFKA_BOOTSTRAP_SERVERS in backend/.env). Exiting.")
        return

    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    print("InstaStock worker starting. Press Ctrl+C to stop.\n", flush=True)

    events.start_publisher()  # the worker also sends the STOCK_CHANGED events it creates
    threads = [
        threading.Thread(target=run_consumer, args=("inventory-worker", KAFKA_ORDER_TOPIC, handle_order_placed), daemon=True),
        threading.Thread(target=run_consumer, args=("search-sync", KAFKA_INVENTORY_TOPIC, handle_stock_changed), daemon=True),
    ]
    for t in threads:
        t.start()
    try:
        while not _stop.is_set():
            _stop.wait(0.5)
    finally:
        print("\nStopping worker...", flush=True)
        _stop.set()
        for t in threads:
            t.join(timeout=5)
        events.stop_publisher()
        db.close_pool()


if __name__ == "__main__":
    main()

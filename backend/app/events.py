"""
Kafka PRODUCER side + the transactional OUTBOX publisher.

Why an outbox?
  The order and its event are saved in PostgreSQL in ONE transaction (orders.py).
  This module then reads unsent events from the outbox_events table and sends
  them to Kafka. If Kafka is down for a minute, nothing is lost: the events
  simply wait in the table and are sent when Kafka is back.

A background thread does this every second (and immediately after each order).
"""
import json
import logging
import threading

from . import db
from .config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_ENABLED, is_configured, kafka_client_config

log = logging.getLogger("instastock.events")

_producer = None
_producer_lock = threading.Lock()
_wakeup = threading.Event()
_stop = threading.Event()
_thread = None

# What the website footer shows about Kafka
_state = {"status": "pending", "detail": "Starting the Kafka producer..."}


def kafka_mode() -> str:
    if not KAFKA_ENABLED:
        return "disabled"
    if not is_configured(KAFKA_BOOTSTRAP_SERVERS):
        return "not-configured"
    return "kafka"


def get_producer():
    """One shared KafkaProducer (it is thread-safe)."""
    global _producer
    with _producer_lock:
        if _producer is None:
            from kafka import KafkaProducer

            _producer = KafkaProducer(
                client_id="instastock-api",
                acks="all",                 # wait until Kafka has safely stored the event
                retries=3,
                linger_ms=5,
                request_timeout_ms=15000,
                max_block_ms=15000,
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                **kafka_client_config(),
            )
        return _producer


def _reset_producer():
    global _producer
    with _producer_lock:
        if _producer is not None:
            try:
                _producer.close(timeout=2)
            except Exception:
                pass
            _producer = None


def publish_pending(batch_size: int = 50) -> int:
    """
    Sends unsent outbox rows to Kafka and marks them as sent.
    FOR UPDATE SKIP LOCKED: if the API and the worker both run this at the same
    time, each row is picked by only one of them.
    """
    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT id, topic, event_type, event_key, payload FROM outbox_events
             WHERE published_at IS NULL
             ORDER BY id
             LIMIT %s
             FOR UPDATE SKIP LOCKED
            """,
            (batch_size,),
        ).fetchall()
        if not rows:
            return 0

        producer = get_producer()
        sent, failure = 0, None
        for row in rows:
            try:
                meta = producer.send(row["topic"], key=row["event_key"], value=row["payload"]).get(timeout=15)
            except Exception as e:
                failure = e
                conn.execute(
                    "UPDATE outbox_events SET publish_attempts = publish_attempts + 1, last_error = %s WHERE id = %s",
                    (f"{type(e).__name__}: {e}"[:500], row["id"]),
                )
                break
            conn.execute(
                "UPDATE outbox_events SET published_at = now(), publish_attempts = publish_attempts + 1, "
                "last_error = NULL WHERE id = %s",
                (row["id"],),
            )
            sent += 1
            print(f"[publisher] {row['event_type']} {row['event_key']} -> {meta.topic} "
                  f"partition {meta.partition}, offset {meta.offset}", flush=True)
        conn.commit()          # keep the rows that WERE sent marked as sent
    if failure is not None:
        raise failure          # the loop below reports it and retries in a few seconds
    return sent


def notify():
    """Called right after an order is saved, so its event is sent immediately."""
    _wakeup.set()


def _loop():
    while not _stop.is_set():
        try:
            get_producer()                       # connects (or raises) before we touch the outbox
            publish_pending()
            _state.update(status="connected", detail="Producer connected to Aiven Kafka")
        except Exception as e:
            _state.update(status="error", detail=f"Kafka not reachable: {type(e).__name__}: {e}")
            print(f"[publisher] Kafka not reachable, retrying in 5 s: {type(e).__name__}: {e}", flush=True)
            _reset_producer()
            _stop.wait(5)
            continue
        _wakeup.wait(timeout=1.0)              # sleep 1 s, or less if an order just came in
        _wakeup.clear()


def start_publisher():
    global _thread
    mode = kafka_mode()
    if mode == "disabled":
        _state.update(status="pending", detail="KAFKA_ENABLED=false: events wait in the outbox, not sent to Kafka")
        return
    if mode == "not-configured":
        _state.update(status="pending", detail="Fill KAFKA_BOOTSTRAP_SERVERS in backend/.env")
        return
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="outbox-publisher", daemon=True)
        _thread.start()


def stop_publisher():
    _stop.set()
    _wakeup.set()
    if _thread is not None:
        _thread.join(timeout=5)
    _reset_producer()


def health() -> dict:
    """Kafka status for /api/health, including how many events are still waiting."""
    status = dict(_state)
    try:
        with db.connection() as conn:
            waiting = conn.execute(
                "SELECT COUNT(*)::int AS n FROM outbox_events WHERE published_at IS NULL"
            ).fetchone()["n"]
        status["detail"] += f" ({waiting} event{'s' if waiting != 1 else ''} waiting in outbox)"
    except Exception:
        pass
    return status


def recent_activity(limit: int = 25) -> dict:
    """Data for the Live events page."""
    with db.connection() as conn:
        outbox = conn.execute(
            """SELECT id, topic, event_type, event_key, created_at, published_at, publish_attempts, last_error
                 FROM outbox_events ORDER BY id DESC LIMIT %s""",
            (limit,),
        ).fetchall()
        consumed = conn.execute(
            """SELECT id, consumer, topic, event_type, event_key, kafka_partition, kafka_offset, detail, processed_at
                 FROM event_log ORDER BY id DESC LIMIT %s""",
            (limit,),
        ).fetchall()
        stats = conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM outbox_events WHERE published_at IS NOT NULL)::int AS published,
                 (SELECT COUNT(*) FROM outbox_events WHERE published_at IS NULL)::int     AS waiting,
                 (SELECT COUNT(*) FROM event_log WHERE consumer = 'inventory-worker')::int AS inventory_worker,
                 (SELECT COUNT(*) FROM event_log WHERE consumer = 'search-sync')::int      AS search_sync,
                 (SELECT MAX(processed_at) FROM event_log)                                 AS last_consumed_at"""
        ).fetchone()
    return {"outbox": outbox, "consumed": consumed, "stats": stats}

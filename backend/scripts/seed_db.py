"""
Creates the tables and loads the product catalog into PostgreSQL.

Run from the backend/ folder (virtual environment active):

    python scripts/seed_db.py           first time: create tables + load products and stock
    python scripts/seed_db.py --reset   DEMO RESET: delete all orders/events and reload stock

Products, cities and stock come from data/products.json.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets us import app.*

import psycopg  # noqa: E402

from app.config import BACKEND_DIR, DATABASE_URL, is_configured  # noqa: E402


def main():
    reset = "--reset" in sys.argv
    if not is_configured(DATABASE_URL):
        sys.exit("DATABASE_URL is not filled in backend/.env. Paste your Aiven PostgreSQL Service URI there first.")

    data = json.loads((BACKEND_DIR / "data" / "products.json").read_text(encoding="utf-8"))
    schema = (BACKEND_DIR / "sql" / "schema.sql").read_text(encoding="utf-8")

    started = time.time()
    print("Connecting to PostgreSQL ...")
    # One transaction: if anything fails, nothing is half-loaded.
    with psycopg.connect(DATABASE_URL, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            print("Creating tables (if they don't exist) ...")
            cur.execute(schema)

            if reset:
                print("--reset: deleting orders, events, stock and products ...")
                cur.execute(
                    "TRUNCATE event_log, outbox_events, order_items, orders, inventory, products, cities "
                    "RESTART IDENTITY CASCADE"
                )

            cur.execute("SELECT COUNT(*) FROM products")
            if cur.fetchone()[0] > 0:
                print("Products already loaded. Nothing to do. (Use --reset to wipe orders and reload stock.)")
                return

            print(f"Loading {len(data['cities'])} cities ...")
            cur.executemany(
                "INSERT INTO cities (name, sort_order) VALUES (%s, %s)",
                [(name, n) for n, name in enumerate(data["cities"], start=1)],
            )

            print(f"Loading {len(data['products'])} products ...")
            cur.executemany(
                """INSERT INTO products (id, sku, name, brand, category, price, mrp, rating,
                                         rating_count, image_url, description, tags)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (p["id"], p["sku"], p["name"], p["brand"], p["category"], p["price"], p["mrp"],
                     p["rating"], p["rating_count"], p["image_url"], p["description"], p["tags"])
                    for p in data["products"]
                ],
            )

            stock_rows = [
                (p["id"], city, units)
                for p in data["products"]
                for city, units in p["stock"].items()
            ]
            print(f"Loading {len(stock_rows)} stock rows (product x city) ...")
            cur.executemany(
                "INSERT INTO inventory (product_id, city, on_hand) VALUES (%s, %s, %s)",
                stock_rows,
            )

            cur.execute("SELECT COUNT(*), COALESCE(SUM(on_hand), 0) FROM inventory")
            rows, units = cur.fetchone()

    print(f"\nDone in {time.time() - started:.1f}s: {len(data['products'])} products, "
          f"{rows} stock rows, {units} units in stock.")
    if reset:
        print("Demo reset complete.")


if __name__ == "__main__":
    try:
        main()
    except psycopg.OperationalError as e:
        sys.exit(f"Could not connect to PostgreSQL: {e}\n"
                 "Check DATABASE_URL in backend/.env and that the Aiven service shows 'Running'.")

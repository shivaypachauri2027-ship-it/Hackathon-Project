"""
RACE TEST: many shoppers try to buy the LAST unit at the same instant.

Run from the backend/ folder while the API is running (virtual environment active):

    python scripts/race_test.py                       10 buyers, Sony WH-1000XM5, Bengaluru
    python scripts/race_test.py --buyers 25 --product 5 --city Pune

What it does:
  1. Sets the product's stock in that city so EXACTLY 1 unit is available.
  2. Fires all orders at the API at the same moment (one thread per buyer).
  3. Prints who won. Correct result: exactly 1 order succeeds, the rest get
     "Not enough stock" (HTTP 409). No overselling.
"""
import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets us import app.*

import psycopg  # noqa: E402

from app.config import DATABASE_URL  # noqa: E402

API = "http://127.0.0.1:8000/api/orders"


def make_exactly_one_available(product_id: int, city: str) -> str:
    """on_hand = reserved + 1  ->  available (on_hand - reserved) = 1"""
    with psycopg.connect(DATABASE_URL, connect_timeout=15) as conn:
        row = conn.execute(
            """UPDATE inventory i SET on_hand = i.reserved + 1, updated_at = now()
                 FROM products p
                WHERE p.id = i.product_id AND i.product_id = %s AND i.city = %s
            RETURNING p.name""",
            (product_id, city),
        ).fetchone()
    if row is None:
        sys.exit(f"No stock row for product {product_id} in {city}.")
    return row[0]


def buy(buyer_no: int, product_id: int, city: str, start: threading.Barrier, results: list):
    body = json.dumps({
        "city": city,
        "customer": {"name": f"Race Buyer {buyer_no}", "phone": f"98765{buyer_no:05d}",
                     "address": "Race test street, demo layout"},
        "items": [{"product_id": product_id, "quantity": 1}],
    }).encode()
    request = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    start.wait()                       # every thread waits here, then all fire together
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as res:
            data = json.loads(res.read())
            results.append((buyer_no, res.status, f"WON  order {data['order_number']}", time.perf_counter() - t0))
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read() or b"{}").get("detail", e.reason)
        results.append((buyer_no, e.code, f"lost ({detail})", time.perf_counter() - t0))
    except Exception as e:
        results.append((buyer_no, 0, f"ERROR {type(e).__name__}: {e}", time.perf_counter() - t0))


def main():
    parser = argparse.ArgumentParser(description="Oversell race test")
    parser.add_argument("--product", type=int, default=5, help="product id (default 5 = Sony WH-1000XM5)")
    parser.add_argument("--city", default="Bengaluru")
    parser.add_argument("--buyers", type=int, default=10)
    args = parser.parse_args()

    name = make_exactly_one_available(args.product, args.city)
    print(f"Stock set: exactly 1 x '{name}' available in {args.city}.")
    print(f"{args.buyers} buyers will now try to buy it at the same moment...\n")

    start = threading.Barrier(args.buyers)
    results: list = []
    threads = [threading.Thread(target=buy, args=(n, args.product, args.city, start, results))
               for n in range(1, args.buyers + 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for buyer_no, status, text, secs in sorted(results):
        print(f"  Buyer {buyer_no:>2}: HTTP {status}  {text}  ({secs * 1000:.0f} ms)")

    winners = sum(1 for r in results if r[1] == 201)
    print(f"\nResult: {winners} order succeeded, {len(results) - winners} were refused.")
    if winners == 1:
        print("PASS: the last unit was sold exactly once. No overselling.")
    else:
        print("CHECK THIS: expected exactly 1 winner.")


if __name__ == "__main__":
    main()

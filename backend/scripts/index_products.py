"""
Copies every product (with its current stock per city) from PostgreSQL into OpenSearch.

Run from the backend/ folder (virtual environment active):

    python scripts/index_products.py             create the index if needed and load all products
    python scripts/index_products.py --recreate  delete and rebuild the index from scratch

After this, the search-sync Kafka worker keeps OpenSearch up to date on every order.
Then try a typo search:  python scripts/index_products.py --try bluetoth
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets us import app.*

from app import db, search  # noqa: E402
from app.config import OPENSEARCH_INDEX  # noqa: E402


def main():
    if not search.is_enabled():
        sys.exit("OpenSearch is not configured: fill OPENSEARCH_URL in backend/.env (and OPENSEARCH_ENABLED=true).")

    if "--try" in sys.argv:
        q = " ".join(sys.argv[sys.argv.index("--try") + 1:]) or "bluetoth"
        res = search.search_products(q=q, city="Bengaluru")
        print(f"Search '{q}' -> {res['total']} results ({res['search_mode']})")
        if res.get("did_you_mean"):
            print(f"Did you mean: {res['did_you_mean']}")
        for item in res["items"][:10]:
            print(f"  - {item['name']}  (Rs {item['price']}, {item['stock_in_city']} in Bengaluru)")
        return

    started = time.time()
    created = search.create_index(recreate="--recreate" in sys.argv)
    print(f"Index '{OPENSEARCH_INDEX}': {'created' if created else 'already exists'}")

    docs = search.load_docs()
    print(f"Read {len(docs)} products with live stock from PostgreSQL ...")
    count = search.index_docs(docs)
    print(f"Indexed {count} products into OpenSearch in {time.time() - started:.1f}s.")
    print("\nTry it:  python scripts/index_products.py --try bluetoth")


if __name__ == "__main__":
    try:
        main()
    finally:
        db.close_pool()  # close PostgreSQL connections so their slots are free again

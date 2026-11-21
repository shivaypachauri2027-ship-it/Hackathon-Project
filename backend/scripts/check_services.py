"""
Checks that your Aiven credentials in backend/.env actually work.

Run from the backend/ folder (with the virtual environment active):
    python scripts/check_services.py

It never prints passwords. Each service is tested independently, so one failure
does not hide the others.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets us import app.config

from app import config  # noqa: E402

OK, FAIL, SKIP = "[ OK ]", "[FAIL]", "[SKIP]"
results = []


def report(status, name, message):
    results.append(status)
    print(f"{status} {name}: {message}")


def check_postgres():
    if not config.is_configured(config.DATABASE_URL):
        return report(SKIP, "PostgreSQL", "DATABASE_URL is not filled in yet (backend/.env)")
    try:
        import psycopg

        with psycopg.connect(config.DATABASE_URL, connect_timeout=15) as conn:
            version = conn.execute("SELECT version()").fetchone()[0]
        report(OK, "PostgreSQL", version.split(",")[0])
    except Exception as e:  # show the real error, it is the fastest way to debug
        report(FAIL, "PostgreSQL", f"{type(e).__name__}: {e}")
        print("       Hint: copy the full 'Service URI' from Aiven (it ends with ?sslmode=require).")


def check_opensearch():
    if not config.is_configured(config.OPENSEARCH_URL):
        return report(SKIP, "OpenSearch", "OPENSEARCH_URL is not filled in yet (backend/.env)")
    try:
        from opensearchpy import OpenSearch

        client = OpenSearch(hosts=[config.OPENSEARCH_URL], use_ssl=True, verify_certs=True, timeout=20)
        info = client.info()
        report(OK, "OpenSearch", f"version {info['version']['number']} (cluster '{info['cluster_name']}')")
    except Exception as e:
        report(FAIL, "OpenSearch", f"{type(e).__name__}: {e}")
        print("       Hint: use the 'Service URI' that starts with https://avnadmin:...")


def check_kafka():
    if not config.is_configured(config.KAFKA_BOOTSTRAP_SERVERS):
        return report(SKIP, "Kafka", "KAFKA_BOOTSTRAP_SERVERS is not filled in yet (backend/.env)")

    try:
        cfg = config.kafka_client_config()
    except Exception as e:
        return report(FAIL, "Kafka", f"{type(e).__name__}: {e} (download the files from the Aiven console into backend/certs/)")
    try:
        from kafka import KafkaAdminClient

        admin = KafkaAdminClient(client_id="instastock-check", request_timeout_ms=20000, **cfg)
        topics = set(admin.list_topics())
        admin.close()
        wanted = {config.KAFKA_ORDER_TOPIC, config.KAFKA_INVENTORY_TOPIC}
        missing = wanted - topics
        if missing:
            report(FAIL, "Kafka", f"connected, but these topics are missing: {', '.join(sorted(missing))} "
                                  "(create them in Aiven console -> Topics, 2 partitions each)")
        else:
            report(OK, "Kafka", f"connected, topics found: {', '.join(sorted(wanted))}")
    except Exception as e:
        report(FAIL, "Kafka", f"{type(e).__name__}: {e}")
        print("       Hint: run  python scripts/kafka_debug.py  to see exactly which step fails.")


if __name__ == "__main__":
    print("Checking services using backend/.env ...\n")
    check_postgres()
    check_opensearch()
    check_kafka()
    print()
    if FAIL in results:
        print("Some checks failed. Paste the output above to your mentor.")
        sys.exit(1)
    print("Done. [SKIP] just means that service is not configured yet.")

"""
Settings for the whole backend.

Every secret (database password, Kafka certificates, OpenSearch password) lives in
backend/.env, which is listed in .gitignore and is NEVER pushed to GitHub.
backend/.env.example shows the same keys with fake values.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ folder (this file is backend/app/config.py)
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def is_configured(value: str) -> bool:
    """False when a value is empty or still the placeholder from .env.example."""
    return bool(value) and "YOUR_" not in value and "your-" not in value


def backend_path(relative: str) -> Path:
    """Turn a path like 'certs/ca.pem' into an absolute path inside backend/."""
    p = Path(relative)
    return p if p.is_absolute() else BACKEND_DIR / p


# ---------- General ----------
DEFAULT_CITY = "Bengaluru"
CORS_ORIGINS = [o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

# ---------- PostgreSQL ----------
DATABASE_URL = env("DATABASE_URL")

# ---------- Kafka ----------
KAFKA_ENABLED = env_bool("KAFKA_ENABLED", True)
KAFKA_BOOTSTRAP_SERVERS = env("KAFKA_BOOTSTRAP_SERVERS")
KAFKA_SECURITY_PROTOCOL = env("KAFKA_SECURITY_PROTOCOL", "SSL").upper()
KAFKA_SSL_CAFILE = env("KAFKA_SSL_CAFILE", "certs/ca.pem")
KAFKA_SSL_CERTFILE = env("KAFKA_SSL_CERTFILE", "certs/service.cert")
KAFKA_SSL_KEYFILE = env("KAFKA_SSL_KEYFILE", "certs/service.key")
KAFKA_SASL_MECHANISM = env("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256")
KAFKA_SASL_USERNAME = env("KAFKA_SASL_USERNAME")
KAFKA_SASL_PASSWORD = env("KAFKA_SASL_PASSWORD")
KAFKA_ORDER_TOPIC = env("KAFKA_ORDER_TOPIC", "order-events")
KAFKA_INVENTORY_TOPIC = env("KAFKA_INVENTORY_TOPIC", "inventory-events")

# ---------- OpenSearch ----------
OPENSEARCH_ENABLED = env_bool("OPENSEARCH_ENABLED", True)
OPENSEARCH_URL = env("OPENSEARCH_URL")
OPENSEARCH_INDEX = env("OPENSEARCH_INDEX", "products")


def kafka_ssl_context():
    """
    TLS settings for Kafka. Certificates are fully verified (CA chain + host name).
    Python 3.13+ also enforces an extra rule (VERIFY_X509_STRICT) that rejects some
    private CA certificates, such as Aiven's Kafka CA, with
    "CA cert does not include key usage extension". We switch off ONLY that rule.
    """
    import ssl

    cafile = backend_path(KAFKA_SSL_CAFILE)
    if not cafile.exists():
        raise FileNotFoundError(f"Kafka CA certificate not found: {cafile}")
    ctx = ssl.create_default_context(cafile=str(cafile))
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if KAFKA_SECURITY_PROTOCOL == "SSL":
        certfile, keyfile = backend_path(KAFKA_SSL_CERTFILE), backend_path(KAFKA_SSL_KEYFILE)
        for f in (certfile, keyfile):
            if not f.exists():
                raise FileNotFoundError(f"Kafka certificate file not found: {f}")
        ctx.load_cert_chain(str(certfile), str(keyfile))
    return ctx


def kafka_client_config() -> dict:
    """
    Connection settings shared by every Kafka client we create (kafka-python).
    Aiven's default is client-certificate auth (SSL): three files in backend/certs/.
    """
    cfg = {
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
        "security_protocol": KAFKA_SECURITY_PROTOCOL,
        "ssl_context": kafka_ssl_context(),
    }
    if KAFKA_SECURITY_PROTOCOL == "SASL_SSL":
        cfg["sasl_mechanism"] = KAFKA_SASL_MECHANISM
        cfg["sasl_plain_username"] = KAFKA_SASL_USERNAME
        cfg["sasl_plain_password"] = KAFKA_SASL_PASSWORD
    return cfg

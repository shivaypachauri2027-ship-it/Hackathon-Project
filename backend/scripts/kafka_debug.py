"""
Finds out WHY Kafka says "NoBrokersAvailable". Run from backend/ (venv active):

    python scripts/kafka_debug.py

It tests, one step at a time: DNS -> network port -> TLS certificates -> Kafka.
The first step that fails tells you exactly what to fix. Never prints passwords.
"""
import logging
import socket
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # lets us import app.*

from app import config  # noqa: E402


def main():
    servers = config.KAFKA_BOOTSTRAP_SERVERS.replace("https://", "").replace("http://", "").strip("/")
    if ":" not in servers:
        sys.exit("KAFKA_BOOTSTRAP_SERVERS must look like  host:port")
    host, port = servers.rsplit(":", 1)
    port = int(port)
    protocol = config.KAFKA_SECURITY_PROTOCOL
    print(f"Kafka address: {host}  port {port}  protocol {protocol}\n")

    # 1. DNS
    try:
        ip = socket.gethostbyname(host)
        print(f"[1] DNS OK: {host} -> {ip}")
    except OSError as e:
        sys.exit(f"[1] DNS FAILED: {e}\n    -> The host name is wrong. Copy the Service URI from Aiven again.")

    # 2. Network
    try:
        socket.create_connection((host, port), timeout=10).close()
        print(f"[2] Network OK: port {port} is reachable")
    except OSError as e:
        sys.exit(f"[2] Cannot reach port {port}: {e}\n"
                 "    -> Either the port is wrong (each authentication method has its own port),\n"
                 "       or this Wi-Fi blocks it. Try a phone hotspot to check.")

    # 3. TLS + certificates (exactly the settings the app uses)
    try:
        ctx = config.kafka_ssl_context()
    except (ssl.SSLError, OSError) as e:
        sys.exit(f"[3] Certificate files can't be loaded: {e}\n"
                 "    -> One of ca.pem / service.cert / service.key is missing, damaged or the wrong file. Download again.")
    try:
        with socket.create_connection((host, port), timeout=10) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                tls.settimeout(3)
                try:
                    tls.recv(1)       # if Kafka rejects our client certificate, the error shows up here
                except socket.timeout:
                    pass              # silence = Kafka accepted us and is waiting for a request
                print(f"[3] TLS OK ({tls.version()}): certificates accepted")
    except ssl.SSLCertVerificationError as e:
        sys.exit(f"[3] Kafka's certificate is not trusted: {e.verify_message}\n"
                 "    -> ca.pem is not the CA certificate of THIS Kafka service. Download it again.")
    except (ssl.SSLError, ConnectionResetError) as e:
        sys.exit(f"[3] TLS was rejected: {type(e).__name__}: {e}\n"
                 "    -> If protocol is SSL: service.cert / service.key don't belong to this service,\n"
                 "       or this port is the SASL port. In Aiven pick 'Client certificate' and use THAT port.\n"
                 "    -> If you meant SASL: set KAFKA_SECURITY_PROTOCOL=SASL_SSL plus username/password.")
    except OSError as e:
        sys.exit(f"[3] TLS failed: {type(e).__name__}: {e}")

    # Extra info: would Python's strict default check (3.13+) have rejected this CA?
    try:
        strict = ssl.create_default_context(cafile=str(config.backend_path(config.KAFKA_SSL_CAFILE)))
        with socket.create_connection((host, port), timeout=10) as raw:
            with strict.wrap_socket(raw, server_hostname=host):
                pass
    except ssl.SSLCertVerificationError as e:
        print(f"    note: Python's strict check alone would fail here ({e.verify_message}); "
              "the app relaxes only that rule, so this is handled.")
    except OSError:
        pass

    # 4. Kafka itself
    import kafka
    from kafka import KafkaAdminClient

    print(f"[4] Talking to Kafka with kafka-python {getattr(kafka, '__version__', '')} ...")
    logging.basicConfig(level=logging.WARNING, format="    kafka log: %(message)s")
    try:
        admin = KafkaAdminClient(client_id="instastock-debug", request_timeout_ms=20000, **config.kafka_client_config())
        topics = sorted(t for t in admin.list_topics() if not t.startswith("__"))
        admin.close()
        print(f"[4] Kafka OK. Topics: {', '.join(topics) or '(none)'}")
    except Exception as e:
        sys.exit(f"[4] Kafka client failed: {type(e).__name__}: {e}\n"
                 "    -> Steps 1-3 passed, so send this whole output to your mentor.")


if __name__ == "__main__":
    main()

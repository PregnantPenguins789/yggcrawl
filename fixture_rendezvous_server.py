#!/usr/bin/env python3
"""Local fixture rendezvous server for testing seed discovery.

Generates properly signed test records and serves them via HTTP.
No Yggdrasil required — tests the rendezvous adapter logic locally.
"""

import json
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from cryptography.hazmat.primitives.asymmetric import ed25519

from logger import logger
import rfc8785


# Generate a test keypair
test_private_key = ed25519.Ed25519PrivateKey.generate()
test_public_key = test_private_key.public_key()

test_pubkey_raw = test_public_key.public_bytes_raw()
test_pubkey_b64 = base64.b64encode(test_pubkey_raw).decode("utf-8")
test_pubkey_str = f"ed25519:{test_pubkey_b64}"

logger.info(f"Test operator pubkey: {test_pubkey_str}")


def create_signed_record(service_type, endpoints):
    """Create a signed service record."""
    record = {
        "version": 1,
        "operator_pubkey": test_pubkey_str,
        "service_type": service_type,
        "endpoints": endpoints,
    }

    # Canonicalize and sign (without signature field)
    canonical = rfc8785.dumps(record)
    signature_bytes = test_private_key.sign(canonical)
    signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")
    record["signature"] = signature_b64

    return record


# Test records
TEST_RECORDS = [
    # Record 1: Yggdrasil endpoint (should be enqueued)
    create_signed_record(
        "dictd",
        [{"network": "yggdrasil", "address": "[200:1111:2222:3333::1]:8080"}],
    ),
    # Record 2: Multiple endpoints (filter for yggdrasil only)
    create_signed_record(
        "web-server",
        [
            {"network": "yggdrasil", "address": "[200:aaaa:bbbb:cccc::2]:9000"},
            {"network": "clearnet", "address": "example.com:8080"},
            {"network": "tor", "address": "something.onion:8080"},
        ],
    ),
    # Record 3: Clearnet only (should not be enqueued)
    create_signed_record(
        "api",
        [{"network": "clearnet", "address": "api.example.com:443"}],
    ),
    # Record 4: Another yggdrasil endpoint
    create_signed_record(
        "git-server",
        [{"network": "yggdrasil", "address": "[200:feed:face:cafe::3]:3000"}],
    ),
]

logger.info(f"Generated {len(TEST_RECORDS)} test records")


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/v1/services":
            self._serve_services()
        elif self.path == "/api/v1/services.sha256":
            self._serve_services_hash()
        else:
            self.send_error(404, "Not found")

    def _serve_services(self):
        response_data = {"records": TEST_RECORDS}
        response_bytes = json.dumps(response_data).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

        logger.info(f"Served {len(TEST_RECORDS)} test records")

    def _serve_services_hash(self):
        response_data = {"records": TEST_RECORDS}
        response_bytes = json.dumps(response_data).encode("utf-8")
        digest = hashlib.sha256(response_bytes).hexdigest()
        hash_str = f"sha256:{digest}"
        hash_bytes = hash_str.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(hash_bytes)))
        self.end_headers()
        self.wfile.write(hash_bytes)

        logger.info(f"Served hash: {hash_str[:16]}...")

    def log_message(self, format, *args):
        logger.debug(f"HTTP: {format % args}")


def run_fixture_server(host="127.0.0.1", port=9999):
    """Run the fixture rendezvous server."""
    logger.info(f"Starting fixture rendezvous server on {host}:{port}")
    logger.info(f"Endpoint: http://{host}:{port}/api/v1/services")
    logger.info("")

    server = HTTPServer((host, port), FixtureHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Fixture server stopped")
        server.server_close()


if __name__ == "__main__":
    run_fixture_server()

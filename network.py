import config
import hashlib
import json
import os
import socket
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Tuple

from logger import logger

PORT = 8080
FETCH_TIMEOUT = 10
MAX_SNAPSHOT_BYTES = 5_000_000  # 5 MB

class IPv6HTTPServer(HTTPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True

class SnapshotHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            logger.debug(f"Request path: {self.path!r}")

            if self.path == "/current.json":
                filepath = config.SNAPSHOT_FILE
            elif self.path == "/current.json.sha256":
                filepath = config.SNAPSHOT_HASH_FILE
            else:
                logger.warning(f"SnapshotHandler: unknown path {self.path!r}")
                self.send_error(404, "Not found")
                return

            logger.debug(f"Resolved file path: {filepath!r}")

            if not os.path.exists(filepath):
                logger.warning(f"SnapshotHandler: missing file {filepath!r}")
                self.send_error(404, "File not found")
                return

            with open(filepath, "rb") as f:
                data = f.read()

            logger.debug(f"Serving {len(data)} bytes from {filepath!r}")

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            logger.error(f"SnapshotHandler error on {self.path!r}: {e!r}")
            try:
                self.send_error(500, "Internal server error")
            except Exception:
                pass

    def log_message(self, format, *args):
        return


def run_server(host: str = "::", port: int = PORT):
    server = IPv6HTTPServer((host, port), SnapshotHandler)
    logger.info(f"Serving snapshots on [{host or '::'}]:{port}")
    server.serve_forever()


def _fetch_url(url: str, *, timeout: int = FETCH_TIMEOUT) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def fetch_verified_snapshot(
    peer_url: str,
    *,
    timeout: int = FETCH_TIMEOUT,
    max_snapshot_bytes: int = MAX_SNAPSHOT_BYTES,
    retries: int = 1,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Fetch snapshot from peer with strict verification.

    Order:
    1. Fetch .sha256
    2. Fetch .json bytes
    3. Enforce size limit
    4. Compute local SHA256
    5. Compare before parsing
    6. Parse only on match
    """
    last_error = None

    for _ in range(retries + 1):
        try:
            hash_url = f"{peer_url}/current.json.sha256"
            peer_hash = _fetch_url(hash_url, timeout=timeout).decode("utf-8").strip()

            json_url = f"{peer_url}/current.json"
            with urllib.request.urlopen(json_url, timeout=timeout) as response:
                raw_payload = response.read(max_snapshot_bytes + 1)

            if len(raw_payload) > max_snapshot_bytes:
                return None, f"Snapshot too large: exceeds {max_snapshot_bytes} bytes"

            local_hash = hashlib.sha256(raw_payload).hexdigest()

            if local_hash != peer_hash:
                return None, f"Hash mismatch! Peer: {peer_hash}, Local: {local_hash}"

            data = json.loads(raw_payload)
            return data, None

        except Exception as e:
            last_error = str(e)

    return None, last_error

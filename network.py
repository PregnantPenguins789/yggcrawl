import config
import hashlib
import json
import os
import socket
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Tuple, Union

from logger import logger
from url_utils import url_network

PORT = 8080
MAX_SNAPSHOT_BYTES = 5_000_000  # 5 MB
LORA_STORE = getattr(config, "LORA_STORE_DIR", "lora_store")
MAX_LORA_BYTES = 500_000_000  # 500 MB

class IPv6HTTPServer(HTTPServer):
    address_family = socket.AF_INET6
    allow_reuse_address = True

class SnapshotHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            logger.debug(f"Request path: {self.path!r}")

            if self.path == "/current.json":
                self._serve_file(config.SNAPSHOT_FILE, "application/json")
            elif self.path == "/current.json.sha256":
                self._serve_file(config.SNAPSHOT_HASH_FILE, "text/plain")
            elif self.path == "/lora/":
                self._serve_lora_directory()
            elif self.path.startswith("/lora/"):
                self._serve_lora_file(self.path[len("/lora/"):])
            else:
                logger.warning(f"SnapshotHandler: unknown path {self.path!r}")
                self.send_error(404, "Not found")

        except Exception as e:
            logger.error(f"SnapshotHandler error on {self.path!r}: {e!r}")
            try:
                self.send_error(500, "Internal server error")
            except Exception:
                pass

    def _serve_file(self, filepath, content_type):
        if not os.path.exists(filepath):
            logger.warning(f"SnapshotHandler: missing file {filepath!r}")
            self.send_error(404, "File not found")
            return

        with open(filepath, "rb") as f:
            data = f.read()

        logger.debug(f"Serving {len(data)} bytes from {filepath!r}")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_lora_directory(self):
        store = LORA_STORE
        if not os.path.isdir(store):
            self._send_json({"adapters": []})
            return

        adapters = []
        for fname in sorted(os.listdir(store)):
            if not fname.endswith(".bin"):
                continue
            name = fname[:-4]
            fpath = os.path.join(store, fname)
            hash_path = os.path.join(store, f"{name}.sha256")
            entry = {
                "name": name,
                "size_bytes": os.path.getsize(fpath),
                "hash_available": os.path.exists(hash_path),
                "url": f"/lora/{name}.bin",
                "hash_url": f"/lora/{name}.sha256",
            }
            adapters.append(entry)

        self._send_json({"adapters": adapters})

    def _serve_lora_file(self, filename):
        # Only allow .bin and .sha256 — no path traversal
        if "/" in filename or "\\" in filename:
            self.send_error(400, "Invalid filename")
            return
        if not (filename.endswith(".bin") or filename.endswith(".sha256")):
            self.send_error(400, "Only .bin and .sha256 files are served")
            return

        filepath = os.path.join(LORA_STORE, filename)
        filepath = os.path.realpath(filepath)
        store_real = os.path.realpath(LORA_STORE)

        # Path traversal guard
        if not filepath.startswith(store_real + os.sep):
            self.send_error(403, "Forbidden")
            return

        if not os.path.exists(filepath):
            self.send_error(404, "Adapter not found")
            return

        if os.path.getsize(filepath) > MAX_LORA_BYTES:
            self.send_error(413, "Adapter file too large")
            return

        content_type = "application/octet-stream" if filename.endswith(".bin") else "text/plain"
        self._serve_file(filepath, content_type)

    def _send_json(self, data):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def run_server(host: str = "::", port: int = PORT):
    server = IPv6HTTPServer((host, port), SnapshotHandler)
    logger.info(f"Serving snapshots on [{host or '::'}]:{port}")
    server.serve_forever()


def _fetch_url(url: str, *, timeout: Union[float, Tuple[float, float]]) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def fetch_verified_snapshot(
    peer_url: str,
    *,
    timeout: Optional[Tuple[float, float]] = None,
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

    Timeout is automatically selected based on peer network (mesh vs clearnet).
    Can be overridden by passing explicit timeout tuple (connect_timeout, read_timeout).
    """
    last_error = None

    # Use per-network timeout if not explicitly provided
    if timeout is None:
        network_class = url_network(peer_url)
        timeout = config.TIMEOUTS[network_class]

    for _ in range(retries + 1):
        try:
            hash_url = f"{peer_url}/current.json.sha256"
            peer_hash = _fetch_url(hash_url, timeout=timeout).decode("utf-8").strip()

            json_url = f"{peer_url}/current.json"
            with urllib.request.urlopen(json_url, timeout=timeout) as response:
                raw_payload = response.read(max_snapshot_bytes + 1)

            if len(raw_payload) > max_snapshot_bytes:
                return None, f"Snapshot too large: exceeds {max_snapshot_bytes} bytes"

            local_hash = f"sha256:{hashlib.sha256(raw_payload).hexdigest()}"

            if local_hash != peer_hash:
                return None, f"Hash mismatch! Peer: {peer_hash}, Local: {local_hash}"

            data = json.loads(raw_payload)
            return data, None

        except Exception as e:
            last_error = str(e)

    return None, last_error

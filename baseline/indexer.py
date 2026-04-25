import json
import hashlib
import time
import os
import shutil
from config import (
    NODE_ID,
    SCHEMA_VERSION,
    SNAPSHOT_FILE,
    SNAPSHOT_HASH_FILE,
    ARCHIVE_DIR,
)
from logger import logger

class Indexer:
    def __init__(self):
        self.index = {}

    def add_record(self, url: str, content: str):
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        fetched_at = int(time.time())

        self.index[url] = {
            "fetched_at": fetched_at,
            "content_hash": content_hash,
        }
        logger.info(f"Indexed {url}: hash={content_hash[:16]}...")

    def save_snapshot(self):
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "node_id": NODE_ID,
            "timestamp": int(time.time()),
            "records": [
                {"url": url, **data}
                for url, data in sorted(self.index.items())
            ],
        }

        os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)

        json_bytes = json.dumps(
            snapshot,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")

        snapshot_hash = hashlib.sha256(json_bytes).hexdigest()

        with open(SNAPSHOT_FILE, "wb") as f:
            f.write(json_bytes)

        with open(SNAPSHOT_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(snapshot_hash + "\n")

        logger.info(f"Snapshot saved: {len(self.index)} records")
        return snapshot_hash

    def archive_snapshot(self):
        if not os.path.exists(SNAPSHOT_FILE):
            logger.warning("No snapshot to archive")
            return

        os.makedirs(ARCHIVE_DIR, exist_ok=True)

        timestamp = int(time.time())
        archive_file = os.path.join(ARCHIVE_DIR, f"snapshot_{timestamp}.json")
        archive_hash_file = archive_file + ".sha256"

        shutil.copy(SNAPSHOT_FILE, archive_file)
        shutil.copy(SNAPSHOT_HASH_FILE, archive_hash_file)

        logger.info(f"Archived snapshot to {archive_file}")

import json
import hashlib
import time
import os
import shutil
from datetime import datetime
from typing import Optional

import config
from logger import logger
from validator import validate_snapshot, validate_diff


class Indexer:
    def __init__(self):
        self.records = []
        self.index = {}  # Added to support fast lookups and state reporting

    def verify_snapshot_files(self):
        """Checks if the snapshot and its hash file exist and match."""
        if not os.path.exists(config.SNAPSHOT_FILE):
            return False, "snapshot file missing"

        if not os.path.exists(config.SNAPSHOT_HASH_FILE):
            return False, "snapshot hash file missing"

        with open(config.SNAPSHOT_FILE, "rb") as f:
            snapshot_bytes = f.read()

        with open(config.SNAPSHOT_HASH_FILE, "r", encoding="utf-8") as f:
            stored_hash = f.read().strip()

        computed_hash = hashlib.sha256(snapshot_bytes).hexdigest()

        if stored_hash != computed_hash:
            return False, "snapshot hash mismatch"

        return True, None

    def add_record(self, url: str, content):
        """
        Add or update a record in the current run.
        Returns: "duplicate", "updated", or "inserted"
        """
        if isinstance(content, dict):
            record = dict(content)
            if "content_hash" not in record or "fetched_at" not in record:
                raise ValueError("record missing required fields")
        elif isinstance(content, str):
            content_bytes = content.encode("utf-8")
            content_hash = hashlib.sha256(content_bytes).hexdigest()
            fetched_at = int(time.time())
            record = {
                "url": url,
                "content_hash": content_hash,
                "fetched_at": fetched_at,
            }
        else:
            raise TypeError("content must be dict or string")

        record["url"] = url
        content_hash = record["content_hash"]
        fetched_at = record["fetched_at"]

        existing = self.index.get(url)
        if existing and existing.get("content_hash") == content_hash:
            return "duplicate"

        self.index[url] = {
            "content_hash": content_hash,
            "fetched_at": fetched_at,
        }

        for existing_record in self.records:
            if existing_record["url"] == url:
                existing_record.clear()
                existing_record.update(record)
                return "updated"

        self.records.append(record)
        return "inserted"

    def load_snapshot(self) -> Optional[dict]:
        """Loads and verifies the existing local snapshot."""
        is_valid, error = self.verify_snapshot_files()
        if not is_valid:
            logger.warning(f"Previous snapshot unavailable: {error}")
            return None

        with open(config.SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        if not validate_snapshot(snapshot):
            return None

        loaded_records = snapshot.get("records", [])
        # Avoid aliasing the loaded snapshot structure. The returned snapshot
        # is treated as an immutable baseline for diffing; Indexer mutates
        # self.records during crawling/merging.
        self.records = [dict(record) for record in loaded_records]
        self.index = {
            record["url"]: {
                "fetched_at": record["fetched_at"],
                "content_hash": record["content_hash"],
            }
            for record in self.records
        }

        logger.info(f"Loaded snapshot: {len(self.records)} records")
        return snapshot

    def diff_against(self, old_snapshot: dict) -> dict:
        """Compares current records against an old snapshot to find changes."""
        old_map = {r["url"]: r["content_hash"] for r in old_snapshot.get("records", [])}
        diff = {"new": [], "changed": [], "unchanged": []}

        for record in sorted(self.records, key=lambda x: x["url"]):
            url = record["url"]
            if url not in old_map:
                diff["new"].append(url)
            elif old_map[url] != record["content_hash"]:
                diff["changed"].append(url)
            else:
                diff["unchanged"].append(url)

        return diff if validate_diff(diff) else {"new": [], "changed": [], "unchanged": []}

    def merge_peer_snapshot(self, peer_data: dict) -> dict:
        """Merges records from a peer snapshot into local records."""
        stats = {"added": 0, "updated": 0, "ignored": 0}
        local_map = {record["url"]: record for record in self.records}

        for peer_record in peer_data.get("records", []):
            url = peer_record["url"]
            peer_fetched_at = peer_record["fetched_at"]
            peer_content_hash = peer_record["content_hash"]

            if url not in local_map:
                new_record = {
                    "url": url,
                    "content_hash": peer_content_hash,
                    "fetched_at": peer_fetched_at,
                }
                self.records.append(new_record)
                local_map[url] = new_record
                self.index[url] = {"content_hash": peer_content_hash, "fetched_at": peer_fetched_at}
                stats["added"] += 1
                continue

            local_record = local_map[url]
            if peer_fetched_at > local_record["fetched_at"]:
                local_record["content_hash"] = peer_content_hash
                local_record["fetched_at"] = peer_fetched_at
                self.index[url] = {"content_hash": peer_content_hash, "fetched_at": peer_fetched_at}
                stats["updated"] += 1
            else:
                stats["ignored"] += 1

        logger.info(
            f"Merged peer snapshot: "
            f"{stats['added']} added, "
            f"{stats['updated']} updated, "
            f"{stats['ignored']} ignored"
        )
        return stats

    def save_snapshot(self) -> str:
        """
        Writes current records to SNAPSHOT_FILE and its hash file.
        Also archives previous snapshot if present.
        """
        snapshot = {
            "node_id": getattr(config, "NODE_ID", "node-local"),
            "schema_version": 1,
            "timestamp": int(time.time()),
            "records": sorted(self.records, key=lambda r: r["url"]),
        }

        if not validate_snapshot(snapshot):
            raise RuntimeError("Refusing to save invalid snapshot")

        snapshot_bytes = json.dumps(snapshot, indent=2, sort_keys=True).encode("utf-8")
        snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()

        temp_path = config.SNAPSHOT_FILE + ".tmp"

        # Archive previous snapshot BEFORE overwrite
        if os.path.exists(config.SNAPSHOT_FILE):
            with open(config.SNAPSHOT_FILE, "rb") as f:
                old_bytes = f.read()
            old_hash = hashlib.sha256(old_bytes).hexdigest()

            archive_path = os.path.join(config.ARCHIVE_DIR, f"{old_hash}.json")
            if not os.path.exists(archive_path):
                with open(archive_path, "wb") as f:
                    f.write(old_bytes)

        # Write snapshot atomically
        with open(temp_path, "wb") as f:
            f.write(snapshot_bytes)

        os.replace(temp_path, config.SNAPSHOT_FILE)

        # Write hash file
        with open(config.SNAPSHOT_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(snapshot_hash)

        return snapshot_hash

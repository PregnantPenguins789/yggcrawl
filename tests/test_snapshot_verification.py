import json
import hashlib
import pytest
from indexer import Indexer
import config

def write_snapshot_files(tmp_path, snapshot_obj, hash_value=None):
    snap_path = tmp_path / "current.json"
    hash_path = tmp_path / "current.json.sha256"

    snapshot_bytes = json.dumps(
        snapshot_obj,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    snap_path.write_bytes(snapshot_bytes)

    if hash_value is None:
        hash_value = f"sha256:{hashlib.sha256(snapshot_bytes).hexdigest()}"

    hash_path.write_text(hash_value + "\n", encoding="utf-8")
    return snap_path, hash_path

def test_load_snapshot_accepts_valid_hash(monkeypatch, tmp_path):
    snapshot = {
        "schema_version": 1,
        "node_id": "node-local",
        "timestamp": 1234567890,
        "records": [
            {
                "url": "http://example.com",
                "fetched_at": 1234567890,
                "content_hash": "abc123",
            }
        ],
    }
    snap_path, hash_path = write_snapshot_files(tmp_path, snapshot)

    monkeypatch.setattr(config, "SNAPSHOT_FILE", str(snap_path))
    monkeypatch.setattr(config, "SNAPSHOT_HASH_FILE", str(hash_path))

    idx = Indexer()
    loaded = idx.load_snapshot()

    assert loaded is not None
    assert "http://example.com" in idx.index
    assert len(idx.records) == 1

def test_load_snapshot_rejects_hash_mismatch(monkeypatch, tmp_path):
    snapshot = {
        "schema_version": 1,
        "node_id": "node-local",
        "timestamp": 1234567890,
        "records": [],
    }
    snap_path, hash_path = write_snapshot_files(
        tmp_path,
        snapshot,
        hash_value="0" * 64,  # Intentionally wrong hash
    )

    monkeypatch.setattr(config, "SNAPSHOT_FILE", str(snap_path))
    monkeypatch.setattr(config, "SNAPSHOT_HASH_FILE", str(hash_path))

    idx = Indexer()
    loaded = idx.load_snapshot()

    assert loaded is None
    assert idx.index == {}

def test_load_snapshot_rejects_missing_hash_file(monkeypatch, tmp_path):
    snapshot = {"schema_version": 1, "node_id": "node-local", "timestamp": 1234567890, "records": []}
    snap_path = tmp_path / "current.json"
    hash_path = tmp_path / "current.json.sha256"

    snap_path.write_text(json.dumps(snapshot))

    monkeypatch.setattr(config, "SNAPSHOT_FILE", str(snap_path))
    monkeypatch.setattr(config, "SNAPSHOT_HASH_FILE", str(hash_path))

    idx = Indexer()
    loaded = idx.load_snapshot()

    assert loaded is None
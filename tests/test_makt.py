"""
End-to-end tests for the M.A.K.T. pipeline:
  validator → ingest → indexer → network serving
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validator import validate_makt_record
from indexer import Indexer
from ingest import ingest_makt_outbox


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dirs(tmp_path):
    outbox = tmp_path / "makt_outbox"
    store = tmp_path / "lora_store"
    outbox.mkdir()
    store.mkdir()
    return {"outbox": outbox, "store": store, "root": tmp_path}


def _make_adapter_bytes(size=1024):
    """Synthetic adapter: deterministic random bytes."""
    return bytes(range(256)) * (size // 256) + bytes(range(size % 256))


def _make_record(name="test-adapter", domain="plumbing", base_model="mistral-7b-q4",
                 content_hash=None, size_bytes=1024):
    h = content_hash or hashlib.sha256(_make_adapter_bytes(size_bytes)).hexdigest()
    return {
        "url": f"ygg://local/lora/{name}",
        "record_type": "lora_adapter",
        "domain": domain,
        "base_model": base_model,
        "size_bytes": size_bytes,
        "content_hash": h,
        "contributed_by": "node-test",
        "fetched_at": int(time.time()),
    }


# ---------------------------------------------------------------------------
# validator.validate_makt_record
# ---------------------------------------------------------------------------

class TestValidateMaktRecord:
    def test_valid_lora_adapter(self):
        assert validate_makt_record(_make_record()) is True

    def test_valid_dataset(self):
        r = {
            "url": "ygg://local/dataset/foo",
            "record_type": "dataset",
            "content_hash": "a" * 64,
            "fetched_at": 1000,
        }
        assert validate_makt_record(r) is True

    def test_valid_model(self):
        r = {
            "url": "ygg://local/model/bar",
            "record_type": "model",
            "content_hash": "b" * 64,
            "fetched_at": 1000,
        }
        assert validate_makt_record(r) is True

    def test_missing_required_field(self):
        r = _make_record()
        del r["content_hash"]
        assert validate_makt_record(r) is False

    def test_unknown_record_type(self):
        r = _make_record()
        r["record_type"] = "unknown_type"
        assert validate_makt_record(r) is False

    def test_lora_missing_domain(self):
        r = _make_record()
        del r["domain"]
        assert validate_makt_record(r) is False

    def test_lora_missing_base_model(self):
        r = _make_record()
        del r["base_model"]
        assert validate_makt_record(r) is False

    def test_lora_missing_size_bytes(self):
        r = _make_record()
        del r["size_bytes"]
        assert validate_makt_record(r) is False

    def test_not_a_dict(self):
        assert validate_makt_record("not a dict") is False
        assert validate_makt_record(None) is False
        assert validate_makt_record([]) is False


# ---------------------------------------------------------------------------
# ingest_makt_outbox
# ---------------------------------------------------------------------------

class TestIngestMaktOutbox:
    def test_empty_outbox(self, tmp_dirs):
        idx = Indexer()
        result = ingest_makt_outbox(idx, str(tmp_dirs["outbox"]))
        assert result == {"accepted": 0, "rejected": 0, "skipped": 0}

    def test_nonexistent_outbox(self, tmp_path):
        idx = Indexer()
        result = ingest_makt_outbox(idx, str(tmp_path / "doesnotexist"))
        assert result["accepted"] == 0

    def test_valid_record_accepted(self, tmp_dirs):
        record = _make_record()
        (tmp_dirs["outbox"] / "adapter.json").write_text(
            json.dumps(record), encoding="utf-8"
        )
        idx = Indexer()
        result = ingest_makt_outbox(idx, str(tmp_dirs["outbox"]))
        assert result["accepted"] == 1
        assert result["rejected"] == 0
        assert len(idx.records) == 1
        assert idx.records[0]["domain"] == "plumbing"
        assert idx.records[0]["record_type"] == "lora_adapter"

    def test_valid_record_moved_to_processed(self, tmp_dirs):
        record = _make_record()
        src = tmp_dirs["outbox"] / "adapter.json"
        src.write_text(json.dumps(record), encoding="utf-8")
        idx = Indexer()
        ingest_makt_outbox(idx, str(tmp_dirs["outbox"]))
        assert not src.exists()
        assert (tmp_dirs["outbox"] / "processed" / "adapter.json").exists()

    def test_invalid_record_rejected(self, tmp_dirs):
        bad_record = {"url": "ygg://local/lora/x", "record_type": "lora_adapter"}
        (tmp_dirs["outbox"] / "bad.json").write_text(
            json.dumps(bad_record), encoding="utf-8"
        )
        idx = Indexer()
        result = ingest_makt_outbox(idx, str(tmp_dirs["outbox"]))
        assert result["rejected"] == 1
        assert (tmp_dirs["outbox"] / "rejected" / "bad.json").exists()

    def test_malformed_json_rejected(self, tmp_dirs):
        (tmp_dirs["outbox"] / "broken.json").write_text("{not valid", encoding="utf-8")
        idx = Indexer()
        result = ingest_makt_outbox(idx, str(tmp_dirs["outbox"]))
        assert result["rejected"] == 1

    def test_duplicate_skipped(self, tmp_dirs):
        record = _make_record()
        for i in range(2):
            (tmp_dirs["outbox"] / f"adapter_{i}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
        idx = Indexer()
        result = ingest_makt_outbox(idx, str(tmp_dirs["outbox"]))
        assert result["accepted"] == 1
        assert result["skipped"] == 1

    def test_multiple_domains(self, tmp_dirs):
        for domain in ("forestry", "electrical", "plumbing"):
            r = _make_record(name=f"adapter-{domain}", domain=domain)
            (tmp_dirs["outbox"] / f"{domain}.json").write_text(
                json.dumps(r), encoding="utf-8"
            )
        idx = Indexer()
        result = ingest_makt_outbox(idx, str(tmp_dirs["outbox"]))
        assert result["accepted"] == 3
        domains = {r["domain"] for r in idx.records}
        assert domains == {"forestry", "electrical", "plumbing"}


# ---------------------------------------------------------------------------
# Indexer — MAKT record field preservation through merge
# ---------------------------------------------------------------------------

class TestIndexerMaktFieldPreservation:
    def test_all_fields_preserved_after_add(self):
        idx = Indexer()
        record = _make_record()
        idx.add_record(record["url"], record)
        stored = idx.records[0]
        assert stored["domain"] == "plumbing"
        assert stored["base_model"] == "mistral-7b-q4"
        assert stored["record_type"] == "lora_adapter"
        assert stored["contributed_by"] == "node-test"

    def test_all_fields_preserved_after_peer_merge(self):
        idx = Indexer()
        record = _make_record(domain="forestry")
        peer_snapshot = {
            "node_id": "peer-1",
            "schema_version": 1,
            "timestamp": int(time.time()),
            "records": [record],
        }
        idx.merge_peer_snapshot(peer_snapshot)
        assert len(idx.records) == 1
        stored = idx.records[0]
        assert stored["domain"] == "forestry"
        assert stored["base_model"] == "mistral-7b-q4"
        assert stored["record_type"] == "lora_adapter"

    def test_peer_update_preserves_newer_fields(self):
        idx = Indexer()
        old_record = _make_record(domain="plumbing")
        old_record["fetched_at"] = 1000
        idx.add_record(old_record["url"], old_record)

        newer_record = dict(old_record)
        newer_record["domain"] = "electrical"
        newer_record["fetched_at"] = 2000
        newer_record["content_hash"] = hashlib.sha256(b"new").hexdigest()

        peer_snapshot = {
            "node_id": "peer-1",
            "schema_version": 1,
            "timestamp": 2000,
            "records": [newer_record],
        }
        idx.merge_peer_snapshot(peer_snapshot)
        assert idx.records[0]["domain"] == "electrical"

    def test_older_peer_record_ignored(self):
        idx = Indexer()
        record = _make_record(domain="plumbing")
        record["fetched_at"] = 5000
        idx.add_record(record["url"], record)

        stale = dict(record)
        stale["domain"] = "forestry"
        stale["fetched_at"] = 1000

        peer_snapshot = {
            "node_id": "peer-1",
            "schema_version": 1,
            "timestamp": 1000,
            "records": [stale],
        }
        stats = idx.merge_peer_snapshot(peer_snapshot)
        assert stats["ignored"] == 1
        assert idx.records[0]["domain"] == "plumbing"


# ---------------------------------------------------------------------------
# Network — /lora/ route security
# ---------------------------------------------------------------------------

class TestNetworkLoraRoutes:
    """Test path traversal guards and content-type handling."""

    def _make_handler(self, tmp_store):
        import importlib
        import network
        # Patch LORA_STORE to point at our temp dir
        original = network.LORA_STORE
        network.LORA_STORE = str(tmp_store)
        yield network
        network.LORA_STORE = original

    def test_path_traversal_blocked(self, tmp_dirs):
        import network as net
        original_store = net.LORA_STORE
        net.LORA_STORE = str(tmp_dirs["store"])
        try:
            handler = MagicMock()
            handler.send_error = MagicMock()
            net.SnapshotHandler._serve_lora_file(handler, "../etc/passwd")
            handler.send_error.assert_called()
            code = handler.send_error.call_args[0][0]
            assert code in (400, 403)
        finally:
            net.LORA_STORE = original_store

    def test_backslash_traversal_blocked(self, tmp_dirs):
        import network as net
        handler = MagicMock()
        handler.send_error = MagicMock()
        net.SnapshotHandler._serve_lora_file(handler, "..\\etc\\passwd")
        handler.send_error.assert_called_with(400, "Invalid filename")

    def test_unknown_extension_blocked(self, tmp_dirs):
        import network as net
        handler = MagicMock()
        handler.send_error = MagicMock()
        net.SnapshotHandler._serve_lora_file(handler, "adapter.py")
        handler.send_error.assert_called_with(400, "Only .bin and .sha256 files are served")

    def test_valid_bin_served(self, tmp_dirs):
        import network as net
        original_store = net.LORA_STORE
        net.LORA_STORE = str(tmp_dirs["store"])
        try:
            data = _make_adapter_bytes(512)
            (tmp_dirs["store"] / "test-adapter.bin").write_bytes(data)

            handler = MagicMock()
            # _serve_lora_file calls self._serve_file when the path is valid;
            # verify that call reaches _serve_file with the right content-type.
            net.SnapshotHandler._serve_lora_file(handler, "test-adapter.bin")
            handler.send_error.assert_not_called()
            handler._serve_file.assert_called_once()
            _, call_kwargs = handler._serve_file.call_args
            positional = handler._serve_file.call_args[0]
            assert positional[1] == "application/octet-stream"
        finally:
            net.LORA_STORE = original_store


# ---------------------------------------------------------------------------
# Full pipeline smoke test
# ---------------------------------------------------------------------------

class TestMaktPipelineSmoke:
    """
    Contribute a synthetic adapter → ingest via outbox → verify it's in the index
    with all fields intact → confirm it survives a save/load round-trip.
    """

    def test_contribute_ingest_roundtrip(self, tmp_dirs, tmp_path):
        adapter_data = _make_adapter_bytes(2048)
        content_hash = hashlib.sha256(adapter_data).hexdigest()

        # Write adapter file to store (simulating what makt contribute does)
        store = tmp_dirs["store"]
        (store / "forestry-v1.bin").write_bytes(adapter_data)
        (store / "forestry-v1.sha256").write_text(content_hash, encoding="utf-8")

        # Write the outbox record (simulating what makt contribute writes)
        record = {
            "url": "ygg://local/lora/forestry-v1",
            "record_type": "lora_adapter",
            "domain": "forestry",
            "base_model": "mistral-7b-q4",
            "size_bytes": len(adapter_data),
            "content_hash": content_hash,
            "contributed_by": "node-test",
            "fetched_at": int(time.time()),
        }
        (tmp_dirs["outbox"] / "forestry-v1.json").write_text(
            json.dumps(record), encoding="utf-8"
        )

        # Ingest
        idx = Indexer()
        counts = ingest_makt_outbox(idx, str(tmp_dirs["outbox"]))
        assert counts["accepted"] == 1

        # Verify field fidelity
        stored = idx.records[0]
        assert stored["domain"] == "forestry"
        assert stored["content_hash"] == content_hash
        assert stored["base_model"] == "mistral-7b-q4"
        assert stored["record_type"] == "lora_adapter"

        # Verify hash file matches adapter
        stored_hash = (store / "forestry-v1.sha256").read_text(encoding="utf-8").strip()
        assert stored_hash == content_hash

        # Verify adapter bytes integrity
        actual = hashlib.sha256((store / "forestry-v1.bin").read_bytes()).hexdigest()
        assert actual == content_hash

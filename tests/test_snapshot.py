from indexer import Indexer
import config

def test_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOT_FILE", str(tmp_path / "snap.json"))
    monkeypatch.setattr(config, "SNAPSHOT_HASH_FILE", str(tmp_path / "snap.json.sha256"))

    idx = Indexer()
    idx.add_record("http://example.com", "<html>ok</html>")
    h = idx.save_snapshot()

    with open(config.SNAPSHOT_HASH_FILE) as f:
        stored = f.read().strip()

    assert h == stored

def test_load_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOT_FILE", str(tmp_path / "snap.json"))
    monkeypatch.setattr(config, "SNAPSHOT_HASH_FILE", str(tmp_path / "snap.json.sha256"))

    idx = Indexer()
    idx.add_record("http://example.com", "<html>ok</html>")
    idx.save_snapshot()

    loaded = idx.load_snapshot()

    assert loaded is not None
    assert loaded["node_id"] == config.NODE_ID
    assert loaded["schema_version"] == config.SCHEMA_VERSION
    assert len(loaded["records"]) == 1
    assert loaded["records"][0]["url"] == "http://example.com"

def test_load_snapshot_hash_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOT_FILE", str(tmp_path / "snap.json"))
    monkeypatch.setattr(config, "SNAPSHOT_HASH_FILE", str(tmp_path / "snap.json.sha256"))

    idx = Indexer()
    idx.add_record("http://example.com", "<html>ok</html>")
    idx.save_snapshot()

    with open(config.SNAPSHOT_HASH_FILE, "w") as f:
        f.write("deadbeef\n")

    loaded = idx.load_snapshot()

    assert loaded is None


def test_load_snapshot_does_not_alias_returned_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOT_FILE", str(tmp_path / "snap.json"))
    monkeypatch.setattr(config, "SNAPSHOT_HASH_FILE", str(tmp_path / "snap.json.sha256"))

    idx = Indexer()
    idx.add_record("http://example.com", "<html>ok</html>")
    idx.save_snapshot()

    snapshot = idx.load_snapshot()
    assert snapshot is not None
    assert len(snapshot["records"]) == 1

    idx.add_record("http://new.example", "<html>new</html>")

    # The returned snapshot should remain an immutable baseline for diffing.
    assert len(snapshot["records"]) == 1
    assert snapshot["records"][0]["url"] == "http://example.com"

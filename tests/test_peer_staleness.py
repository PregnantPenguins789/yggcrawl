from peer_sync import is_peer_snapshot_stale, sync_from_peers


def test_peer_snapshot_rejected_if_older():
    local = {"timestamp": 200}
    peer = {"timestamp": 100}
    assert is_peer_snapshot_stale(local, peer) is True


def test_peer_snapshot_accepted_if_newer():
    local = {"timestamp": 100}
    peer = {"timestamp": 200}
    assert is_peer_snapshot_stale(local, peer) is False


def test_peer_snapshot_accepted_if_equal():
    local = {"timestamp": 100}
    peer = {"timestamp": 100}
    assert is_peer_snapshot_stale(local, peer) is False


def test_peer_snapshot_accepted_if_missing_timestamp():
    local = {"timestamp": 100}
    peer = {}
    assert is_peer_snapshot_stale(local, peer) is False


def test_stale_peer_not_merged(monkeypatch):
    # Mocking a stale peer and a fresh peer
    peer_responses = [
        ({"timestamp": 100, "records": []}, None),  # Stale
        ({"timestamp": 300, "records": []}, None),  # Fresh
    ]
    
    # Simple iterator to return different peer data
    it = iter(peer_responses)
    monkeypatch.setattr("peer_sync.fetch_verified_snapshot", lambda url: next(it))
    monkeypatch.setattr("peer_sync.validate_snapshot", lambda snapshot: True)

    calls = {"merged": 0}

    class DummyIndexer:
        def load_snapshot(self):
            return {"timestamp": 200, "records": []}

        def merge_peer_snapshot(self, snapshot):
            calls["merged"] += 1
            return {"added": 0, "updated": 0, "ignored": 0}

    totals = sync_from_peers(DummyIndexer(), ["peer_stale", "peer_fresh"])

    # Should only merge the fresh one
    assert calls["merged"] == 1
    assert totals["peers_total"] == 2
    assert totals["peers_ok"] == 1
    assert totals["ignored"] == 1


def test_sync_from_peers_accumulates_merges(monkeypatch, tmp_path):
    import config
    import indexer as indexer_mod
    from indexer import Indexer

    # Create a valid local snapshot on disk so Indexer.load_snapshot behaves
    # like the real node.
    monkeypatch.setattr(config, "SNAPSHOT_FILE", str(tmp_path / "current.json"))
    monkeypatch.setattr(config, "SNAPSHOT_HASH_FILE", str(tmp_path / "current.json.sha256"))
    monkeypatch.setattr(config, "ARCHIVE_DIR", str(tmp_path / "archive"))
    (tmp_path / "archive").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(indexer_mod.time, "time", lambda: 1)

    idx = Indexer()
    idx.save_snapshot()  # empty baseline snapshot

    peer_a = {
        "node_id": "peer-a",
        "schema_version": 1,
        "timestamp": 2,
        "records": [{"url": "http://a.com", "content_hash": "ha", "fetched_at": 10}],
    }
    peer_b = {
        "node_id": "peer-b",
        "schema_version": 1,
        "timestamp": 3,
        "records": [{"url": "http://b.com", "content_hash": "hb", "fetched_at": 20}],
    }

    it = iter([(peer_a, None), (peer_b, None)])
    monkeypatch.setattr("peer_sync.fetch_verified_snapshot", lambda url: next(it))
    monkeypatch.setattr("peer_sync.validate_snapshot", lambda snapshot: True)

    totals = sync_from_peers(idx, ["peer-a", "peer-b"])

    assert totals["peers_total"] == 2
    assert totals["peers_ok"] == 2
    assert totals["added"] == 2
    assert sorted(r["url"] for r in idx.records) == ["http://a.com", "http://b.com"]

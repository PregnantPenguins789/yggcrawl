import pytest
from indexer import Indexer

def test_merge_latest_timestamp_wins():
    idx = Indexer()
    # Local has an old version of example.com
    idx.records = [{
        "url": "http://example.com",
        "content_hash": "old_hash",
        "fetched_at": 1000
    }]
    
    peer_data = {
        "records": [{
            "url": "http://example.com",
            "content_hash": "new_hash",
            "fetched_at": 2000  # Newer
        }]
    }
    
    stats = idx.merge_peer_snapshot(peer_data)
    
    assert stats["updated"] == 1
    assert idx.records[0]["content_hash"] == "new_hash"

def test_merge_ignores_older_peer_data():
    idx = Indexer()
    idx.records = [{
        "url": "http://example.com",
        "content_hash": "fresh_hash",
        "fetched_at": 5000
    }]
    
    peer_data = {
        "records": [{
            "url": "http://example.com",
            "content_hash": "stale_hash",
            "fetched_at": 1000 # Older
        }]
    }
    
    stats = idx.merge_peer_snapshot(peer_data)
    
    assert stats["ignored"] == 1
    assert idx.records[0]["content_hash"] == "fresh_hash"

def test_merge_maintains_deterministic_order():
    idx = Indexer()
    idx.records = [{"url": "z.com", "content_hash": "h1", "fetched_at": 1}]

    peer_data = {
        "records": [
            {"url": "a.com", "content_hash": "h2", "fetched_at": 1},
            {"url": "m.com", "content_hash": "h3", "fetched_at": 1},
        ]
    }

    idx.merge_peer_snapshot(peer_data)

    urls = [r["url"] for r in sorted(idx.records, key=lambda r: r["url"])]
    assert urls == ["a.com", "m.com", "z.com"]
from indexer import Indexer


def snapshot(records, node_id="peer", timestamp=1):
    return {
        "node_id": node_id,
        "schema_version": 1,
        "timestamp": timestamp,
        "records": records,
    }


def records_map(indexer):
    return {r["url"]: r for r in indexer.records}


def test_merge_two_peers_same_result_regardless_of_order():
    peer_a = snapshot([
        {"url": "http://x.com", "content_hash": "hash_x_old", "fetched_at": 100},
        {"url": "http://a.com", "content_hash": "hash_a", "fetched_at": 100},
    ], node_id="peer-a")

    peer_b = snapshot([
        {"url": "http://x.com", "content_hash": "hash_x_new", "fetched_at": 500},
        {"url": "http://b.com", "content_hash": "hash_b", "fetched_at": 200},
    ], node_id="peer-b")

    idx1 = Indexer()
    idx1.merge_peer_snapshot(peer_a)
    idx1.merge_peer_snapshot(peer_b)

    idx2 = Indexer()
    idx2.merge_peer_snapshot(peer_b)
    idx2.merge_peer_snapshot(peer_a)

    map1 = records_map(idx1)
    map2 = records_map(idx2)

    assert map1 == map2
    assert map1["http://x.com"]["content_hash"] == "hash_x_new"
    assert map1["http://x.com"]["fetched_at"] == 500
    assert "http://a.com" in map1
    assert "http://b.com" in map1


def test_latest_timestamp_wins_across_multiple_peers():
    peers = [
        snapshot([
            {"url": "http://x.com", "content_hash": "hash1", "fetched_at": 100},
        ], node_id="peer-1"),
        snapshot([
            {"url": "http://x.com", "content_hash": "hash2", "fetched_at": 300},
        ], node_id="peer-2"),
        snapshot([
            {"url": "http://x.com", "content_hash": "hash3", "fetched_at": 200},
        ], node_id="peer-3"),
    ]

    idx = Indexer()
    for peer in peers:
        idx.merge_peer_snapshot(peer)

    final = records_map(idx)["http://x.com"]
    assert final["content_hash"] == "hash2"
    assert final["fetched_at"] == 300


def test_stale_peer_cannot_roll_back_newer_state():
    idx = Indexer()
    idx.records = [
        {"url": "http://x.com", "content_hash": "local_new", "fetched_at": 1000}
    ]

    stale_peer = snapshot([
        {"url": "http://x.com", "content_hash": "peer_old", "fetched_at": 50},
    ], node_id="stale-peer")

    stats = idx.merge_peer_snapshot(stale_peer)
    final = records_map(idx)["http://x.com"]

    assert stats["added"] == 0
    assert stats["updated"] == 0
    assert stats["ignored"] == 1
    assert final["content_hash"] == "local_new"
    assert final["fetched_at"] == 1000


def test_multi_peer_union_of_new_urls():
    peer_a = snapshot([
        {"url": "http://a.com", "content_hash": "ha", "fetched_at": 10},
    ], node_id="peer-a")

    peer_b = snapshot([
        {"url": "http://b.com", "content_hash": "hb", "fetched_at": 20},
    ], node_id="peer-b")

    peer_c = snapshot([
        {"url": "http://c.com", "content_hash": "hc", "fetched_at": 30},
    ], node_id="peer-c")

    idx = Indexer()
    idx.merge_peer_snapshot(peer_a)
    idx.merge_peer_snapshot(peer_b)
    idx.merge_peer_snapshot(peer_c)

    urls = sorted(r["url"] for r in idx.records)
    assert urls == ["http://a.com", "http://b.com", "http://c.com"]


def test_equal_timestamps_keep_existing_local_record():
    idx = Indexer()
    idx.records = [
        {"url": "http://x.com", "content_hash": "local_hash", "fetched_at": 100}
    ]

    peer = snapshot([
        {"url": "http://x.com", "content_hash": "peer_hash", "fetched_at": 100},
    ], node_id="peer-equal")

    stats = idx.merge_peer_snapshot(peer)
    final = records_map(idx)["http://x.com"]

    assert stats["added"] == 0
    assert stats["updated"] == 0
    assert stats["ignored"] == 1
    assert final["content_hash"] == "local_hash"
    assert final["fetched_at"] == 100
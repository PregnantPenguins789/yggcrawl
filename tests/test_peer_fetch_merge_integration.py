import json
import hashlib
from unittest.mock import patch, MagicMock

from indexer import Indexer
from network import fetch_verified_snapshot
from validator import validate_snapshot


def make_response(body: bytes):
    response = MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    return response


def make_snapshot(node_id, timestamp, records):
    return {
        "node_id": node_id,
        "schema_version": 1,
        "timestamp": timestamp,
        "records": records,
    }


def records_map(indexer):
    return {r["url"]: r for r in indexer.records}


def test_fetch_merge_two_peers_converges_regardless_of_order():
    peer1_snapshot = make_snapshot(
        "peer-1",
        100,
        [
            {"url": "http://x.com", "content_hash": "hash_x_old", "fetched_at": 100},
            {"url": "http://a.com", "content_hash": "hash_a", "fetched_at": 100},
        ],
    )
    peer2_snapshot = make_snapshot(
        "peer-2",
        200,
        [
            {"url": "http://x.com", "content_hash": "hash_x_new", "fetched_at": 500},
            {"url": "http://b.com", "content_hash": "hash_b", "fetched_at": 200},
        ],
    )

    peer1_bytes = json.dumps(peer1_snapshot).encode("utf-8")
    peer2_bytes = json.dumps(peer2_snapshot).encode("utf-8")

    peer1_hash = hashlib.sha256(peer1_bytes).hexdigest().encode("utf-8")
    peer2_hash = hashlib.sha256(peer2_bytes).hexdigest().encode("utf-8")

    # Order 1: peer1 then peer2
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = [
            make_response(peer1_hash),
            make_response(peer1_bytes),
            make_response(peer2_hash),
            make_response(peer2_bytes),
        ]

        idx1 = Indexer()

        data1, err1 = fetch_verified_snapshot("http://peer1")
        assert err1 is None
        assert validate_snapshot(data1) is True
        idx1.merge_peer_snapshot(data1)

        data2, err2 = fetch_verified_snapshot("http://peer2")
        assert err2 is None
        assert validate_snapshot(data2) is True
        idx1.merge_peer_snapshot(data2)

    # Order 2: peer2 then peer1
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = [
            make_response(peer2_hash),
            make_response(peer2_bytes),
            make_response(peer1_hash),
            make_response(peer1_bytes),
        ]

        idx2 = Indexer()

        data2, err2 = fetch_verified_snapshot("http://peer2")
        assert err2 is None
        assert validate_snapshot(data2) is True
        idx2.merge_peer_snapshot(data2)

        data1, err1 = fetch_verified_snapshot("http://peer1")
        assert err1 is None
        assert validate_snapshot(data1) is True
        idx2.merge_peer_snapshot(data1)

    map1 = records_map(idx1)
    map2 = records_map(idx2)

    assert map1 == map2
    assert sorted(map1.keys()) == [
        "http://a.com",
        "http://b.com",
        "http://x.com",
    ]
    assert map1["http://x.com"]["content_hash"] == "hash_x_new"
    assert map1["http://x.com"]["fetched_at"] == 500
    assert map1["http://a.com"]["content_hash"] == "hash_a"
    assert map1["http://b.com"]["content_hash"] == "hash_b"
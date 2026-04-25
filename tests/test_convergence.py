import json
import hashlib
from unittest.mock import patch, MagicMock

from indexer import Indexer
from network import fetch_verified_snapshot
from validator import validate_snapshot


def test_two_node_convergence():
    node_a = Indexer()
    node_a.records = [
        {"url": "http://x.com", "content_hash": "hash_old", "fetched_at": 100}
    ]

    node_b_records = [
        {"url": "http://x.com", "content_hash": "hash_new", "fetched_at": 500},
        {"url": "http://y.com", "content_hash": "hash_y", "fetched_at": 500},
    ]
    node_b_snapshot = {
        "node_id": "node-b",
        "schema_version": 1,
        "timestamp": 600,
        "records": node_b_records,
    }

    node_b_bytes = json.dumps(node_b_snapshot).encode("utf-8")
    node_b_hash = hashlib.sha256(node_b_bytes).hexdigest()

    with patch("urllib.request.urlopen") as mock_url:
        res_hash = MagicMock()
        res_hash.read.return_value = node_b_hash.encode("utf-8")
        res_hash.__enter__.return_value = res_hash

        res_json = MagicMock()
        res_json.read.return_value = node_b_bytes
        res_json.__enter__.return_value = res_json

        mock_url.side_effect = [res_hash, res_json]

        peer_data, error = fetch_verified_snapshot("http://node-b")
        assert error is None
        assert validate_snapshot(peer_data) is True

        stats = node_a.merge_peer_snapshot(peer_data)

        assert stats["added"] == 1
        assert stats["updated"] == 1
        assert stats["ignored"] == 0

        records_map = {r["url"]: r for r in node_a.records}
        assert records_map["http://x.com"]["content_hash"] == "hash_new"
        assert records_map["http://x.com"]["fetched_at"] == 500
        assert records_map["http://y.com"]["content_hash"] == "hash_y"

        sorted_urls = [r["url"] for r in sorted(node_a.records, key=lambda r: r["url"])]
        assert sorted_urls == ["http://x.com", "http://y.com"]
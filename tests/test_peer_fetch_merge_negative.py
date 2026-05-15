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


def records_map(indexer):
    return {r["url"]: r for r in indexer.records}


def test_bad_peer_is_skipped_while_good_peer_still_merges():
    good_snapshot = {
        "node_id": "good-peer",
        "schema_version": 1,
        "timestamp": 100,
        "records": [
            {
                "url": "http://good.com",
                "content_hash": "good_hash",
                "fetched_at": 100,
            }
        ],
    }
    good_bytes = json.dumps(good_snapshot).encode("utf-8")
    good_hash = f"sha256:{hashlib.sha256(good_bytes).hexdigest()}".encode("utf-8")

    bad_snapshot = {
        "node_id": "bad-peer",
        "schema_version": 1,
        "timestamp": 200,
        "records": [
            {
                "url": "http://bad.com",
                "content_hash": "bad_hash",
                "fetched_at": 200,
            }
        ],
    }
    bad_bytes = json.dumps(bad_snapshot).encode("utf-8")
    wrong_hash = b"definitely_not_the_real_hash"

    idx = Indexer()

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = [
            # bad peer: hash then payload
            make_response(wrong_hash),
            make_response(bad_bytes),
            # good peer: hash then payload
            make_response(good_hash),
            make_response(good_bytes),
        ]

        bad_data, bad_error = fetch_verified_snapshot("http://bad-peer")
        assert bad_data is None
        assert "Hash mismatch" in bad_error

        good_data, good_error = fetch_verified_snapshot("http://good-peer")
        assert good_error is None
        assert validate_snapshot(good_data) is True

        stats = idx.merge_peer_snapshot(good_data)

    final = records_map(idx)

    assert stats["added"] == 1
    assert stats["updated"] == 0
    assert stats["ignored"] == 0
    assert "http://good.com" in final
    assert "http://bad.com" not in final
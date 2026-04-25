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


def test_invalid_schema_peer_is_skipped_while_good_peer_still_merges():
    invalid_snapshot = {
        "node_id": "bad-peer",
        "schema_version": 1,
        "timestamp": 100,
        # invalid: missing "records"
    }
    invalid_bytes = json.dumps(invalid_snapshot).encode("utf-8")
    invalid_hash = hashlib.sha256(invalid_bytes).hexdigest().encode("utf-8")

    good_snapshot = {
        "node_id": "good-peer",
        "schema_version": 1,
        "timestamp": 200,
        "records": [
            {
                "url": "http://good.com",
                "content_hash": "good_hash",
                "fetched_at": 200,
            }
        ],
    }
    good_bytes = json.dumps(good_snapshot).encode("utf-8")
    good_hash = hashlib.sha256(good_bytes).hexdigest().encode("utf-8")

    idx = Indexer()

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = [
            # invalid-schema peer
            make_response(invalid_hash),
            make_response(invalid_bytes),
            # good peer
            make_response(good_hash),
            make_response(good_bytes),
        ]

        bad_data, bad_error = fetch_verified_snapshot("http://bad-peer")
        assert bad_error is None
        assert validate_snapshot(bad_data) is False

        good_data, good_error = fetch_verified_snapshot("http://good-peer")
        assert good_error is None
        assert validate_snapshot(good_data) is True

        stats = idx.merge_peer_snapshot(good_data)

    final = records_map(idx)

    assert stats["added"] == 1
    assert stats["updated"] == 0
    assert stats["ignored"] == 0
    assert "http://good.com" in final
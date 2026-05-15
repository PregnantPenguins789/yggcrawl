import json
import hashlib
from unittest.mock import patch, MagicMock

from network import fetch_verified_snapshot, FETCH_TIMEOUT


def test_fetch_rejects_mismatched_hash_before_parsing():
    malicious_json = b'{"malicious_key": "injected_data"}'
    wrong_hash = "not_the_real_hash_12345"

    with patch("urllib.request.urlopen") as mock_url:
        response_hash = MagicMock()
        response_hash.read.return_value = wrong_hash.encode("utf-8")
        response_hash.__enter__.return_value = response_hash

        response_json = MagicMock()
        response_json.read.return_value = malicious_json
        response_json.__enter__.return_value = response_json

        mock_url.side_effect = [response_hash, response_json]

        with patch("json.loads") as mock_json_loads:
            data, error = fetch_verified_snapshot("http://fake-peer")

            assert data is None
            assert "Hash mismatch" in error
            mock_json_loads.assert_not_called()


def test_fetch_accepts_valid_snapshot():
    valid_data = {"node_id": "test-node", "schema_version": 1, "timestamp": 1, "records": []}
    valid_bytes = json.dumps(valid_data).encode("utf-8")
    correct_hash = f"sha256:{hashlib.sha256(valid_bytes).hexdigest()}"

    with patch("urllib.request.urlopen") as mock_url:
        res_hash = MagicMock()
        res_hash.read.return_value = correct_hash.encode("utf-8")
        res_hash.__enter__.return_value = res_hash

        res_json = MagicMock()
        res_json.read.return_value = valid_bytes
        res_json.__enter__.return_value = res_json

        mock_url.side_effect = [res_hash, res_json]

        data, error = fetch_verified_snapshot("http://fake-peer")

        assert error is None
        assert data["node_id"] == "test-node"


def test_fetch_rejects_oversized_snapshot_before_parsing():
    valid_prefix = b'{"node_id":"x","schema_version":1,"timestamp":1,"records":[]}'
    payload = valid_prefix + b"x" * 200
    correct_hash = hashlib.sha256(payload).hexdigest()

    with patch("urllib.request.urlopen") as mock_url:
        res_hash = MagicMock()
        res_hash.read.return_value = correct_hash.encode("utf-8")
        res_hash.__enter__.return_value = res_hash

        res_json = MagicMock()
        res_json.read.return_value = payload
        res_json.__enter__.return_value = res_json

        mock_url.side_effect = [res_hash, res_json]

        with patch("json.loads") as mock_json_loads:
            data, error = fetch_verified_snapshot(
                "http://fake-peer",
                max_snapshot_bytes=64,
            )

            assert data is None
            assert "Snapshot too large" in error
            mock_json_loads.assert_not_called()


def test_fetch_uses_timeout_for_both_requests():
    valid_data = {"node_id": "test-node", "schema_version": 1, "timestamp": 1, "records": []}
    valid_bytes = json.dumps(valid_data).encode("utf-8")
    correct_hash = f"sha256:{hashlib.sha256(valid_bytes).hexdigest()}"

    with patch("urllib.request.urlopen") as mock_url:
        res_hash = MagicMock()
        res_hash.read.return_value = correct_hash.encode("utf-8")
        res_hash.__enter__.return_value = res_hash

        res_json = MagicMock()
        res_json.read.return_value = valid_bytes
        res_json.__enter__.return_value = res_json

        mock_url.side_effect = [res_hash, res_json]

        data, error = fetch_verified_snapshot("http://fake-peer")

        assert error is None
        assert data is not None

        assert mock_url.call_count == 2
        for call in mock_url.call_args_list:
            assert call.kwargs["timeout"] == FETCH_TIMEOUT


def test_fetch_allows_ipv6_peer_url():
    valid_data = {"node_id": "test-node", "schema_version": 1, "timestamp": 1, "records": []}
    valid_bytes = json.dumps(valid_data).encode("utf-8")
    correct_hash = f"sha256:{hashlib.sha256(valid_bytes).hexdigest()}"

    with patch("urllib.request.urlopen") as mock_url:
        res_hash = MagicMock()
        res_hash.read.return_value = correct_hash.encode("utf-8")
        res_hash.__enter__.return_value = res_hash

        res_json = MagicMock()
        res_json.read.return_value = valid_bytes
        res_json.__enter__.return_value = res_json

        mock_url.side_effect = [res_hash, res_json]

        peer = "http://[200:1111:2222:3333::1]:8080"
        data, error = fetch_verified_snapshot(peer)

        assert error is None
        assert data["node_id"] == "test-node"

        first_url = mock_url.call_args_list[0].args[0]
        second_url = mock_url.call_args_list[1].args[0]

        assert first_url == f"{peer}/current.json.sha256"
        assert second_url == f"{peer}/current.json"
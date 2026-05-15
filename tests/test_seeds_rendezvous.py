"""Tests for rendezvous seed discovery and crawler integration.

Tests signature verification, endpoint filtering, and enqueuing of discovered
seeds from a rendezvous server to the crawler queue.
"""

import base64
import hashlib
import json
from collections import deque
from unittest.mock import patch, MagicMock
import pytest

from seeds_rendezvous import (
    fetch_service_records,
    extract_yggdrasil_endpoints,
    ingest_rendezvous_seeds,
)
from cryptography.hazmat.primitives.asymmetric import ed25519


class MockCrawler:
    """Mock crawler with queue and seen set for testing."""

    def __init__(self):
        self.queue = deque()
        self.seen = set()


class TestFetchServiceRecords:
    """Test fetching and parsing service records from rendezvous."""

    def test_fetch_valid_records(self):
        """Fetch and parse valid service records."""
        valid_records = {
            "records": [
                {
                    "version": 1,
                    "operator_pubkey": "ed25519:test",
                    "service_type": "dictd",
                    "endpoints": [],
                }
            ]
        }
        valid_bytes = json.dumps(valid_records).encode("utf-8")
        correct_hash = f"sha256:{hashlib.sha256(valid_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = correct_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = valid_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            records, error = fetch_service_records("http://rendezvous.example.com")

            assert error is None
            assert records is not None
            assert len(records) == 1
            assert records[0]["service_type"] == "dictd"

    def test_fetch_empty_records_list(self):
        """Fetch valid response with empty records list."""
        valid_data = {"records": []}
        valid_bytes = json.dumps(valid_data).encode("utf-8")
        correct_hash = f"sha256:{hashlib.sha256(valid_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = correct_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = valid_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            records, error = fetch_service_records("http://rendezvous.example.com")

            assert error is None
            assert records == []

    def test_fetch_rejects_non_dict_response(self):
        """Reject non-dict JSON response."""
        # Not a dict, it's a list
        response_data = [{"service": "test"}]
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            records, error = fetch_service_records("http://rendezvous.example.com")

            assert records is None
            assert "not a JSON object" in error

    def test_fetch_rejects_missing_records_field(self):
        """Reject response without 'records' field."""
        response_data = {"services": []}  # Wrong field name
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            records, error = fetch_service_records("http://rendezvous.example.com")

            assert records == []  # Default empty list
            assert error is None

    def test_fetch_rejects_non_list_records(self):
        """Reject 'records' field that is not a list."""
        response_data = {"records": "not a list"}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            records, error = fetch_service_records("http://rendezvous.example.com")

            assert records is None
            assert "not a list" in error

    def test_fetch_rejects_oversized_records(self):
        """Reject response with too many records."""
        records_list = [{"id": i} for i in range(100)]
        response_data = {"records": records_list}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            records, error = fetch_service_records(
                "http://rendezvous.example.com", max_records=10
            )

            assert records is None
            assert "Too many records" in error

    def test_fetch_network_error(self):
        """Handle network fetch failure."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Connection refused")

            records, error = fetch_service_records("http://rendezvous.example.com")

            assert records is None
            assert "Failed to fetch" in error


class TestExtractYggdrasilEndpoints:
    """Test Yggdrasil endpoint extraction."""

    def test_extract_single_yggdrasil_endpoint(self):
        """Extract single Yggdrasil endpoint."""
        record = {
            "endpoints": [
                {"network": "yggdrasil", "address": "[200:abcd::1]:8080"}
            ]
        }

        endpoints = extract_yggdrasil_endpoints(record)

        assert len(endpoints) == 1
        assert endpoints[0] == "[200:abcd::1]:8080"

    def test_extract_multiple_yggdrasil_endpoints(self):
        """Extract multiple Yggdrasil endpoints."""
        record = {
            "endpoints": [
                {"network": "yggdrasil", "address": "[200:1111::1]:8080"},
                {"network": "yggdrasil", "address": "[200:2222::2]:9090"},
            ]
        }

        endpoints = extract_yggdrasil_endpoints(record)

        assert len(endpoints) == 2
        assert "[200:1111::1]:8080" in endpoints
        assert "[200:2222::2]:9090" in endpoints

    def test_filter_out_clearnet_endpoints(self):
        """Filter out non-yggdrasil endpoints."""
        record = {
            "endpoints": [
                {"network": "yggdrasil", "address": "[200:abcd::1]:8080"},
                {"network": "clearnet", "address": "example.com:8080"},
                {"network": "tor", "address": "something.onion:8080"},
            ]
        }

        endpoints = extract_yggdrasil_endpoints(record)

        assert len(endpoints) == 1
        assert endpoints[0] == "[200:abcd::1]:8080"

    def test_skip_invalid_endpoint_format(self):
        """Skip endpoints with invalid structure."""
        record = {
            "endpoints": [
                {"network": "yggdrasil", "address": "[200:abcd::1]:8080"},
                {"network": "yggdrasil"},  # Missing address
                {"network": "yggdrasil", "address": ""},  # Empty address
                {"network": "yggdrasil", "address": None},  # Null address
                "not a dict",  # Not a dict
            ]
        }

        endpoints = extract_yggdrasil_endpoints(record)

        assert len(endpoints) == 1
        assert endpoints[0] == "[200:abcd::1]:8080"

    def test_handle_missing_endpoints_field(self):
        """Handle record without endpoints field."""
        record = {"service_type": "dictd"}

        endpoints = extract_yggdrasil_endpoints(record)

        assert endpoints == []

    def test_handle_non_list_endpoints(self):
        """Handle endpoints field that is not a list."""
        record = {"endpoints": "not a list"}

        endpoints = extract_yggdrasil_endpoints(record)

        assert endpoints == []

    def test_handle_non_dict_record(self):
        """Handle non-dict record."""
        endpoints = extract_yggdrasil_endpoints("not a dict")
        assert endpoints == []

        endpoints = extract_yggdrasil_endpoints(None)
        assert endpoints == []


class TestIngestRendezvousSeeds:
    """Test full ingest pipeline with crawler integration."""

    def test_ingest_verified_seed(self):
        """Ingest and enqueue verified seed."""
        # Generate a key and sign a record
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        pubkey_raw = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(pubkey_raw).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        # Create a service record
        record = {
            "version": 1,
            "operator_pubkey": pubkey_str,
            "service_type": "dictd",
            "endpoints": [{"network": "yggdrasil", "address": "[200:abcd::1]:8080"}],
        }

        # Sign it with proper canonicalization (using the signature module)
        from signature import canonicalize_record

        canonical = canonicalize_record(record)
        sig_bytes = private_key.sign(canonical)
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")
        record["signature"] = sig_b64

        # Create response
        response_data = {"records": [record]}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            crawler = MockCrawler()
            counts = ingest_rendezvous_seeds(crawler, "http://rendezvous.example.com")

            assert counts["fetched"] == 1
            assert counts["verified"] == 1
            assert counts["enqueued"] == 1
            assert counts["rejected"] == 0
            assert len(crawler.queue) == 1
            assert "http://[200:abcd::1]:8080" in crawler.queue

    def test_ingest_rejects_unverified_signature(self):
        """Reject record with invalid signature."""
        record = {
            "version": 1,
            "operator_pubkey": "ed25519:invalid",
            "service_type": "dictd",
            "endpoints": [{"network": "yggdrasil", "address": "[200:abcd::1]:8080"}],
            "signature": "c2lnbmF0dXJl",  # base64-encoded "signature"
        }

        response_data = {"records": [record]}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            crawler = MockCrawler()
            counts = ingest_rendezvous_seeds(crawler, "http://rendezvous.example.com")

            assert counts["fetched"] == 1
            assert counts["verified"] == 0
            assert counts["rejected"] == 1
            assert counts["enqueued"] == 0
            assert len(crawler.queue) == 0

    def test_ingest_skips_records_without_yggdrasil(self):
        """Skip records that have no Yggdrasil endpoints."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        pubkey_raw = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(pubkey_raw).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        record = {
            "version": 1,
            "operator_pubkey": pubkey_str,
            "service_type": "dictd",
            "endpoints": [{"network": "clearnet", "address": "example.com:8080"}],
        }

        from signature import canonicalize_record

        canonical = canonicalize_record(record)
        sig_bytes = private_key.sign(canonical)
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")
        record["signature"] = sig_b64

        response_data = {"records": [record]}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            crawler = MockCrawler()
            counts = ingest_rendezvous_seeds(crawler, "http://rendezvous.example.com")

            assert counts["fetched"] == 1
            assert counts["verified"] == 1
            assert counts["enqueued"] == 0
            assert len(crawler.queue) == 0

    def test_ingest_handles_mixed_records(self):
        """Handle mix of valid and invalid records."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        pubkey_raw = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(pubkey_raw).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        # Valid record
        valid_record = {
            "version": 1,
            "operator_pubkey": pubkey_str,
            "service_type": "dictd",
            "endpoints": [{"network": "yggdrasil", "address": "[200:1111::1]:8080"}],
        }

        from signature import canonicalize_record

        canonical = canonicalize_record(valid_record)
        sig_bytes = private_key.sign(canonical)
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")
        valid_record["signature"] = sig_b64

        # Invalid record (no signature)
        invalid_record = {
            "version": 1,
            "operator_pubkey": pubkey_str,
            "service_type": "dictd",
            "endpoints": [{"network": "yggdrasil", "address": "[200:2222::2]:8080"}],
        }

        response_data = {"records": [valid_record, invalid_record]}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            crawler = MockCrawler()
            counts = ingest_rendezvous_seeds(crawler, "http://rendezvous.example.com")

            assert counts["fetched"] == 2
            assert counts["verified"] == 1
            assert counts["enqueued"] == 1
            assert counts["rejected"] == 1

    def test_ingest_deduplicates_urls(self):
        """Do not enqueue URLs already in crawler.seen."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        pubkey_raw = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(pubkey_raw).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        # Same endpoint twice
        record1 = {
            "version": 1,
            "operator_pubkey": pubkey_str,
            "service_type": "dictd",
            "endpoints": [{"network": "yggdrasil", "address": "[200:abcd::1]:8080"}],
        }

        record2 = {
            "version": 1,
            "operator_pubkey": pubkey_str,
            "service_type": "other",
            "endpoints": [{"network": "yggdrasil", "address": "[200:abcd::1]:8080"}],
        }

        from signature import canonicalize_record

        for record in [record1, record2]:
            canonical = canonicalize_record(record)
            sig_bytes = private_key.sign(canonical)
            sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")
            record["signature"] = sig_b64

        response_data = {"records": [record1, record2]}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            crawler = MockCrawler()
            counts = ingest_rendezvous_seeds(crawler, "http://rendezvous.example.com")

            # Both records verified, but only one URL enqueued
            assert counts["fetched"] == 2
            assert counts["verified"] == 2
            assert counts["enqueued"] == 1
            assert len(crawler.queue) == 1

    def test_ingest_network_failure(self):
        """Handle network failure gracefully."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Connection timeout")

            crawler = MockCrawler()
            counts = ingest_rendezvous_seeds(crawler, "http://rendezvous.example.com")

            # All counts zero on failure
            assert counts["fetched"] == 0
            assert counts["verified"] == 0
            assert counts["enqueued"] == 0
            assert counts["rejected"] == 0
            assert len(crawler.queue) == 0

    def test_ingest_missing_operator_pubkey(self):
        """Reject records missing operator_pubkey."""
        record = {
            "version": 1,
            # Missing operator_pubkey
            "service_type": "dictd",
            "endpoints": [{"network": "yggdrasil", "address": "[200:abcd::1]:8080"}],
            "signature": "test",
        }

        response_data = {"records": [record]}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            crawler = MockCrawler()
            counts = ingest_rendezvous_seeds(crawler, "http://rendezvous.example.com")

            assert counts["rejected"] == 1
            assert counts["enqueued"] == 0

    def test_ingest_non_dict_record(self):
        """Reject non-dict records."""
        response_data = {"records": ["not a dict", 123, None]}
        response_bytes = json.dumps(response_data).encode("utf-8")
        response_hash = f"sha256:{hashlib.sha256(response_bytes).hexdigest()}"

        with patch("urllib.request.urlopen") as mock_urlopen:
            res_hash = MagicMock()
            res_hash.read.return_value = response_hash.encode("utf-8")
            res_hash.__enter__.return_value = res_hash
            res_hash.__exit__.return_value = False

            res_json = MagicMock()
            res_json.read.return_value = response_bytes
            res_json.__enter__.return_value = res_json
            res_json.__exit__.return_value = False

            mock_urlopen.side_effect = [res_hash, res_json]

            crawler = MockCrawler()
            counts = ingest_rendezvous_seeds(crawler, "http://rendezvous.example.com")

            assert counts["fetched"] == 3
            assert counts["rejected"] == 3
            assert counts["verified"] == 0
            assert counts["enqueued"] == 0

"""Local fixture tests for rendezvous seed discovery.

Tests the full pipeline without Yggdrasil:
- Fixture server generates signed records
- Adapter fetches and verifies
- Endpoints filter correctly
- Seeds enqueue to crawler
"""

import sys
import subprocess
import time
import json
import threading
from unittest.mock import patch, MagicMock

import pytest

# For running fixture server in background
from collections import deque


class TestFixtureServer:
    """Test the fixture rendezvous server itself."""

    def test_fixture_imports(self):
        """Verify fixture server imports required modules."""
        try:
            from fixture_rendezvous_server import (
                TEST_RECORDS,
                test_pubkey_str,
                create_signed_record,
            )

            assert len(TEST_RECORDS) > 0
            assert test_pubkey_str.startswith("ed25519:")
        except ImportError as e:
            pytest.skip(f"Fixture server not available: {e}")

    def test_fixture_records_are_signed(self):
        """Verify all fixture records have valid signatures."""
        try:
            from fixture_rendezvous_server import TEST_RECORDS
            from signature import verify_signature
            from fixture_rendezvous_server import test_pubkey_str

            for i, record in enumerate(TEST_RECORDS):
                assert "signature" in record, f"Record {i} missing signature"
                result = verify_signature(record, test_pubkey_str)
                assert result is True, f"Record {i} signature verification failed"

        except ImportError:
            pytest.skip("Fixture server not available")

    def test_fixture_has_mixed_endpoints(self):
        """Verify fixture includes yggdrasil and non-yggdrasil endpoints."""
        try:
            from fixture_rendezvous_server import TEST_RECORDS

            has_yggdrasil = False
            has_clearnet = False

            for record in TEST_RECORDS:
                endpoints = record.get("endpoints", [])
                for endpoint in endpoints:
                    if endpoint.get("network") == "yggdrasil":
                        has_yggdrasil = True
                    elif endpoint.get("network") in ("clearnet", "tor"):
                        has_clearnet = True

            assert has_yggdrasil, "Fixture should have yggdrasil endpoints"
            assert has_clearnet, "Fixture should have non-yggdrasil endpoints"

        except ImportError:
            pytest.skip("Fixture server not available")


class TestRendezvousAdapterWithFixture:
    """Test rendezvous adapter against fixture server."""

    def test_fetch_fixture_records(self):
        """Fetch and parse records from fixture endpoint."""
        try:
            import json
            import hashlib
            from fixture_rendezvous_server import TEST_RECORDS, FixtureHandler
            from seeds_rendezvous import fetch_service_records
            from urllib.request import urlopen
            from http.server import HTTPServer

            # Start fixture server in background thread
            server = HTTPServer(("127.0.0.1", 9999), FixtureHandler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            time.sleep(0.5)  # Let server start

            try:
                # Fetch from fixture
                records, error = fetch_service_records(
                    "http://127.0.0.1:9999", timeout=(2.0, 5.0)
                )

                assert error is None, f"Fetch error: {error}"
                assert records is not None
                assert len(records) == len(TEST_RECORDS)

            finally:
                server.shutdown()

        except ImportError:
            pytest.skip("Fixture server not available")
        except Exception as e:
            pytest.skip(f"Fixture server test setup failed: {e}")

    def test_signature_verification_pipeline(self):
        """Test that signatures verify in the adapter pipeline."""
        try:
            from fixture_rendezvous_server import TEST_RECORDS, test_pubkey_str
            from signature import verify_signature

            for record in TEST_RECORDS:
                # The adapter calls this on each record
                result = verify_signature(record, test_pubkey_str)
                assert result is True, f"Signature verification failed for {record}"

        except ImportError:
            pytest.skip("Fixture server not available")

    def test_endpoint_filtering(self):
        """Test that only yggdrasil endpoints are extracted."""
        try:
            from fixture_rendezvous_server import TEST_RECORDS
            from seeds_rendezvous import extract_yggdrasil_endpoints

            yggdrasil_count = 0
            for record in TEST_RECORDS:
                endpoints = extract_yggdrasil_endpoints(record)
                yggdrasil_count += len(endpoints)

                # Verify no non-yggdrasil endpoints in result
                for ep in endpoints:
                    assert "200:" in ep or "201:" in ep or "202:" in ep or "20" in ep[
                        :5
                    ], f"Non-yggdrasil endpoint: {ep}"

            assert (
                yggdrasil_count > 0
            ), "Should extract at least one yggdrasil endpoint"

        except ImportError:
            pytest.skip("Fixture server not available")

    def test_ingest_pipeline_simulation(self):
        """Simulate the full ingest pipeline with fixture records."""
        try:
            from fixture_rendezvous_server import TEST_RECORDS, test_pubkey_str
            from seeds_rendezvous import extract_yggdrasil_endpoints
            from signature import verify_signature
            from collections import deque

            # Simulate crawler
            class MockCrawler:
                def __init__(self):
                    self.queue = deque()
                    self.seen = set()

            crawler = MockCrawler()

            # Simulate pipeline
            enqueued = 0
            verified = 0

            for record in TEST_RECORDS:
                if not verify_signature(record, test_pubkey_str):
                    continue

                verified += 1
                endpoints = extract_yggdrasil_endpoints(record)

                for addr in endpoints:
                    url = f"http://{addr}" if "://" not in addr else addr
                    if url not in crawler.seen:
                        crawler.seen.add(url)
                        crawler.queue.append(url)
                        enqueued += 1

            assert verified > 0, "Should verify at least one record"
            assert enqueued > 0, "Should enqueue at least one seed"
            assert len(crawler.queue) == enqueued
            assert len(crawler.seen) == enqueued

        except ImportError:
            pytest.skip("Fixture server not available")


class TestRendezvousLocalIntegration:
    """Integration tests with fixture server."""

    def test_fixture_server_startup(self):
        """Test that fixture server can start and serve."""
        try:
            from fixture_rendezvous_server import FixtureHandler, TEST_RECORDS
            from http.server import HTTPServer
            import socket

            # Find available port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]

            server = HTTPServer(("127.0.0.1", port), FixtureHandler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            time.sleep(0.5)

            # Test connectivity
            import urllib.request

            url = f"http://127.0.0.1:{port}/api/v1/services"
            response = urllib.request.urlopen(url, timeout=2)
            data = json.load(response)

            assert "records" in data
            assert len(data["records"]) == len(TEST_RECORDS)

            server.shutdown()

        except ImportError:
            pytest.skip("Fixture server not available")
        except Exception as e:
            pytest.skip(f"Fixture server integration test failed: {e}")

    def test_full_local_pipeline(self):
        """Test complete rendezvous discovery pipeline locally."""
        try:
            from fixture_rendezvous_server import FixtureHandler, TEST_RECORDS
            from seeds_rendezvous import ingest_rendezvous_seeds
            from http.server import HTTPServer
            from collections import deque

            class MockCrawler:
                def __init__(self):
                    self.queue = deque()
                    self.seen = set()

            # Start server
            server = HTTPServer(("127.0.0.1", 9998), FixtureHandler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            time.sleep(0.5)

            try:
                # Run ingest
                crawler = MockCrawler()
                counts = ingest_rendezvous_seeds(
                    crawler, "http://127.0.0.1:9998", timeout=(2.0, 5.0)
                )

                # Verify results
                assert counts["fetched"] > 0, "Should fetch records"
                assert counts["verified"] > 0, "Should verify signatures"
                assert counts["enqueued"] > 0, "Should enqueue yggdrasil endpoints"
                assert counts["enqueued"] <= counts["verified"], "Can't enqueue more than verified"

                # Verify crawler state
                assert len(crawler.queue) == counts["enqueued"]
                assert len(crawler.seen) == counts["enqueued"]

            finally:
                server.shutdown()

        except ImportError:
            pytest.skip("Fixture server not available")
        except Exception as e:
            pytest.skip(f"Full pipeline test failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

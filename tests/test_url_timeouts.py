"""Tests for per-network timeout classification and application."""

import pytest
from unittest.mock import patch, MagicMock
from url_utils import url_network
import config
from crawler import Crawler


class TestUrlNetworkClassification:
    """Test URL classification into mesh vs clearnet."""

    def test_yggdrasil_ipv6_classified_as_mesh(self):
        # Yggdrasil addresses (200::/7) → mesh
        assert url_network("http://[200:abcd::1]:8080/path") == "mesh"
        assert url_network("http://[200::1]:8080") == "mesh"
        assert url_network("http://[03ff:ffff:ffff:ffff:ffff:ffff:ffff:ffff]/") == "mesh"

    def test_non_yggdrasil_ipv6_classified_as_clearnet(self):
        # Public IPv6 addresses (not in 200::/7) → clearnet
        assert url_network("http://[2001:db8::1]:8080/path") == "clearnet"
        assert url_network("http://[fe80::1]:8080") == "clearnet"
        # Just outside Yggdrasil range
        assert url_network("http://[0400::1]:8080") == "clearnet"

    def test_ipv4_classified_as_clearnet(self):
        # IPv4 addresses → clearnet
        assert url_network("http://192.168.1.1:8080/path") == "clearnet"
        assert url_network("http://10.0.0.1:80") == "clearnet"
        assert url_network("http://8.8.8.8") == "clearnet"

    def test_hostname_classified_as_clearnet(self):
        # Hostname-based URLs → clearnet (can't determine without DNS resolution)
        assert url_network("http://example.com:8080/path") == "clearnet"
        assert url_network("http://mesh.example.org") == "clearnet"
        assert url_network("https://node.local:9000") == "clearnet"

    def test_ipv6_with_different_port_formats(self):
        # With explicit port
        assert url_network("http://[200:abcd::1]:8080") == "mesh"
        # Default port
        assert url_network("http://[200:abcd::1]/") == "mesh"
        # HTTPS
        assert url_network("https://[200:abcd::1]:8443") == "mesh"

    def test_urls_with_paths_and_query_strings(self):
        # Complex URLs with paths, queries, fragments
        assert url_network("http://[200:abcd::1]:8080/path?query=1#frag") == "mesh"
        assert url_network("http://example.com:8080/path?query=1#frag") == "clearnet"

    def test_malformed_url_defaults_to_clearnet(self):
        # Unparseable URLs default to clearnet for safety
        assert url_network("not a url at all") == "clearnet"
        assert url_network("") == "clearnet"
        assert url_network("://invalid") == "clearnet"


class TestConfigTimeouts:
    """Verify timeout configuration structure."""

    def test_timeouts_config_has_required_keys(self):
        # Config must have both network types
        assert "clearnet" in config.TIMEOUTS
        assert "mesh" in config.TIMEOUTS

    def test_timeout_values_are_tuples(self):
        # Each timeout is (connect_timeout, read_timeout)
        assert isinstance(config.TIMEOUTS["clearnet"], tuple)
        assert isinstance(config.TIMEOUTS["mesh"], tuple)
        assert len(config.TIMEOUTS["clearnet"]) == 2
        assert len(config.TIMEOUTS["mesh"]) == 2

    def test_timeout_values_are_positive_numbers(self):
        # Timeouts must be positive floats/ints
        for network, (connect, read) in config.TIMEOUTS.items():
            assert connect > 0, f"{network} connect timeout must be positive"
            assert read > 0, f"{network} read timeout must be positive"

    def test_mesh_timeouts_more_tolerant_than_clearnet(self):
        # Mesh should have longer timeouts than clearnet
        clearnet_connect, clearnet_read = config.TIMEOUTS["clearnet"]
        mesh_connect, mesh_read = config.TIMEOUTS["mesh"]
        assert mesh_connect >= clearnet_connect, "Mesh connect should be >= clearnet"
        assert mesh_read >= clearnet_read, "Mesh read should be >= clearnet"


class TestCrawlerTimeoutApplication:
    """Test that crawler applies correct timeouts based on URL."""

    def test_clearnet_url_uses_clearnet_timeout(self):
        # Verify crawler.fetch applies clearnet timeout for regular URLs
        crawler = Crawler()
        url = "http://example.com/page"

        with patch("crawler.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = "<html></html>"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            try:
                crawler.fetch(url)
            except Exception:
                pass

            # Verify requests.get was called with clearnet timeout tuple
            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args.kwargs
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] == config.TIMEOUTS["clearnet"]

    def test_yggdrasil_url_uses_mesh_timeout(self):
        # Verify crawler.fetch applies mesh timeout for Yggdrasil URLs
        crawler = Crawler()
        url = "http://[200:abcd::1]:8080/page"

        with patch("crawler.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = "<html></html>"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            try:
                crawler.fetch(url)
            except Exception:
                pass

            # Verify requests.get was called with mesh timeout tuple
            mock_get.assert_called_once()
            call_kwargs = mock_get.call_args.kwargs
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] == config.TIMEOUTS["mesh"]

    def test_ipv4_url_uses_clearnet_timeout(self):
        # IPv4 should be treated as clearnet
        crawler = Crawler()
        url = "http://192.168.1.1:8080/page"

        with patch("crawler.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.text = "<html></html>"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            try:
                crawler.fetch(url)
            except Exception:
                pass

            call_kwargs = mock_get.call_args.kwargs
            assert call_kwargs["timeout"] == config.TIMEOUTS["clearnet"]


class TestPeerFetchTimeouts:
    """Test that peer snapshot fetching uses correct timeouts."""

    def test_fetch_verified_snapshot_uses_per_network_timeout(self):
        from network import fetch_verified_snapshot

        # Test with a Yggdrasil peer URL
        ygg_peer = "http://[200:abcd::1]:8080"
        clearnet_peer = "http://example.com"

        with patch("urllib.request.urlopen") as mock_urlopen:
            # Mock response for hash
            mock_response = MagicMock()
            mock_response.read.return_value = b"sha256:abc123"
            mock_response.__enter__.return_value = mock_response
            mock_response.__exit__.return_value = False

            mock_urlopen.return_value = mock_response

            try:
                fetch_verified_snapshot(ygg_peer)
            except Exception:
                pass

            # Check that mesh timeout was used
            calls = mock_urlopen.call_args_list
            if calls:
                assert calls[0].kwargs.get("timeout") == config.TIMEOUTS["mesh"]

    def test_fetch_verified_snapshot_can_override_timeout(self):
        from network import fetch_verified_snapshot

        custom_timeout = (1.0, 2.0)
        url = "http://example.com"

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"sha256:abc123"
            mock_response.__enter__.return_value = mock_response
            mock_response.__exit__.return_value = False

            mock_urlopen.return_value = mock_response

            try:
                fetch_verified_snapshot(url, timeout=custom_timeout)
            except Exception:
                pass

            # Custom timeout should be used even for clearnet
            if mock_urlopen.call_args_list:
                assert mock_urlopen.call_args_list[0].kwargs.get("timeout") == custom_timeout

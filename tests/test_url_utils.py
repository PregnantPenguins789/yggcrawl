"""Tests for IPv6-aware URL utilities."""

import pytest
from url_utils import (
    canonicalize_ipv6,
    canonicalize_hostname,
    canonicalize_url,
    is_yggdrasil,
    extract_hostname,
)


class TestCanonicalizeIPv6:
    """Test IPv6 address canonicalization (RFC 5952)."""

    def test_compressed_form_unchanged(self):
        # Already in canonical form
        assert canonicalize_ipv6("200:abcd::1") == "200:abcd::1"

    def test_expands_and_compresses_to_canonical(self):
        # Different representations of the same address
        assert canonicalize_ipv6("0200:abcd:0000:0000:0000:0000:0000:0001") == "200:abcd::1"
        assert canonicalize_ipv6("200:ABCD::1") == "200:abcd::1"

    def test_longest_zero_run_compressed(self):
        # Longest run of zeros gets the ::
        assert canonicalize_ipv6("2001:0db8:0000:0000:0000:0000:0000:0001") == "2001:db8::1"

    def test_non_ipv6_returned_unchanged(self):
        # IPv4
        assert canonicalize_ipv6("192.168.1.1") == "192.168.1.1"
        # Hostname
        assert canonicalize_ipv6("example.com") == "example.com"
        # Empty
        assert canonicalize_ipv6("") == ""


class TestCanonicalizeHostname:
    """Test hostname/port canonicalization with IPv6 support."""

    def test_ipv6_with_port_canonicalized(self):
        # De-compressed form with port
        assert canonicalize_hostname("[0200:abcd::1]:8080") == "[200:abcd::1]:8080"

    def test_ipv6_without_port_canonicalized(self):
        # Just the address in brackets
        assert canonicalize_hostname("[200:ABCD::1]") == "[200:abcd::1]"

    def test_ipv4_with_port_unchanged(self):
        # IPv4 with port — no canonicalization needed
        assert canonicalize_hostname("192.168.1.1:8080") == "192.168.1.1:8080"

    def test_hostname_with_port_unchanged(self):
        # Regular hostname with port
        assert canonicalize_hostname("example.com:8080") == "example.com:8080"

    def test_just_hostname_unchanged(self):
        # No port
        assert canonicalize_hostname("example.com") == "example.com"

    def test_malformed_bracket_returned_unchanged(self):
        # Missing closing bracket
        assert canonicalize_hostname("[200:abcd::1:8080") == "[200:abcd::1:8080"


class TestCanonicalizeUrl:
    """Test full URL canonicalization."""

    def test_ipv6_url_round_trip(self):
        # Full URL with IPv6, port, and path
        url = "http://[0200:abcd::1]:8080/path?query=1#fragment"
        canonical = canonicalize_url(url)
        # Address should be compressed
        assert "[200:abcd::1]" in canonical
        # Port, path, query, fragment should survive round-trip
        assert ":8080/path" in canonical
        assert "query=1" in canonical
        assert "fragment" in canonical

    def test_ipv4_url_unchanged(self):
        # IPv4 URL should be unchanged
        url = "http://192.168.1.1:8080/path"
        assert canonicalize_url(url) == url

    def test_hostname_url_unchanged(self):
        # Regular hostname URL should be unchanged
        url = "http://example.com:8080/path"
        assert canonicalize_url(url) == url

    def test_https_scheme_preserved(self):
        # Scheme should be preserved
        url = "https://[200:abcd::1]:8443/secure"
        canonical = canonicalize_url(url)
        assert canonical.startswith("https://")


class TestIsYggdrasil:
    """Test Yggdrasil address range detection (200::/7)."""

    def test_yggdrasil_range_start(self):
        # Boundary: start of Yggdrasil range
        assert is_yggdrasil("200::") is True
        assert is_yggdrasil("0200::") is True

    def test_yggdrasil_range_middle(self):
        # Common Yggdrasil addresses
        assert is_yggdrasil("200:abcd::1") is True
        assert is_yggdrasil("201:ffff::1") is True

    def test_yggdrasil_range_end(self):
        # Boundary: just before end of Yggdrasil range
        assert is_yggdrasil("03ff:ffff:ffff:ffff:ffff:ffff:ffff:ffff") is True

    def test_outside_yggdrasil_range(self):
        # Just outside the range
        assert is_yggdrasil("0400::") is False
        # Common public IPv6
        assert is_yggdrasil("2001:db8::1") is False

    def test_ipv4_not_yggdrasil(self):
        # IPv4 addresses are never Yggdrasil
        assert is_yggdrasil("192.168.1.1") is False
        assert is_yggdrasil("10.0.0.1") is False

    def test_non_address_not_yggdrasil(self):
        # Hostnames, invalid addresses
        assert is_yggdrasil("example.com") is False
        assert is_yggdrasil("not-an-address") is False
        assert is_yggdrasil("") is False


class TestExtractHostname:
    """Test hostname extraction from netloc strings."""

    def test_ipv6_brackets_with_port(self):
        # Extract address from [addr]:port
        assert extract_hostname("[200:abcd::1]:8080") == "200:abcd::1"

    def test_ipv6_brackets_no_port(self):
        # Just the address in brackets
        assert extract_hostname("[200:abcd::1]") == "200:abcd::1"

    def test_ipv4_with_port(self):
        # IPv4:port → IPv4
        assert extract_hostname("192.168.1.1:8080") == "192.168.1.1"

    def test_hostname_with_port(self):
        # host:port → host
        assert extract_hostname("example.com:8080") == "example.com"

    def test_hostname_no_port(self):
        # Just hostname
        assert extract_hostname("example.com") == "example.com"

    def test_empty_netloc(self):
        # Empty input
        assert extract_hostname("") == ""


class TestIntegrationRoundTrip:
    """Integration tests: ensure URL handling survives round-trips."""

    def test_ipv6_url_deduplication_consistent(self):
        # Two URLs with same address in different forms should canonicalize to same string
        url1 = "http://[0200:abcd::1]:8080/path"
        url2 = "http://[200:ABCD:0000::1]:8080/path"

        canonical1 = canonicalize_url(url1)
        canonical2 = canonicalize_url(url2)

        assert canonical1 == canonical2
        # This proves they'd be deduplicated correctly in a set
        assert len({canonical1, canonical2}) == 1

    def test_ipv6_url_set_deduplication(self):
        # Practical test: add to set with canonicalization
        url1 = "http://[0200:abcd::1]:8080/path"
        url2 = "http://[200:ABCD::1]:8080/path"

        canonical_urls = {canonicalize_url(url) for url in [url1, url2]}
        assert len(canonical_urls) == 1

    def test_mixed_ipv4_ipv6_urls_distinct(self):
        # IPv4 and IPv6 should remain distinct even if canonicalized
        url_ipv4 = "http://192.168.1.1:8080/path"
        url_ipv6 = "http://[200:abcd::1]:8080/path"

        canonical_ipv4 = canonicalize_url(url_ipv4)
        canonical_ipv6 = canonicalize_url(url_ipv6)

        # They should be different
        assert canonical_ipv4 != canonical_ipv6

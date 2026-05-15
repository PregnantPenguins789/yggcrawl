"""URL utilities for mesh-aware crawling."""

import ipaddress
from urllib.parse import urlparse, urlunparse


def canonicalize_ipv6(addr: str) -> str:
    """Return IPv6 address in canonical form (RFC 5952).

    Handles IPv6 addresses by parsing with ipaddress module,
    which automatically produces the compressed canonical form.
    Non-IPv6 input is returned unchanged.
    """
    try:
        # ipaddress.IPv6Address parses and normalizes
        ip = ipaddress.IPv6Address(addr)
        return ip.compressed
    except (ipaddress.AddressValueError, ValueError):
        # Not an IPv6 address, return unchanged
        return addr


def canonicalize_hostname(netloc: str) -> str:
    """Canonicalize hostname/port string, handling IPv6 bracket notation.

    For IPv6 addresses in brackets, extracts the address, canonicalizes it,
    and returns [canonical]:port. For other inputs, returns unchanged.

    Example:
        '[0200:abcd::1]:8080' → '[200:abcd::1]:8080'
        'example.com:8080' → 'example.com:8080'
    """
    if not netloc:
        return netloc

    # Check if this is an IPv6 address in brackets
    if netloc.startswith("["):
        # Find the closing bracket
        bracket_end = netloc.find("]")
        if bracket_end == -1:
            return netloc  # Malformed, return as-is

        addr = netloc[1:bracket_end]
        rest = netloc[bracket_end + 1:]  # May include :port

        canonical_addr = canonicalize_ipv6(addr)
        return f"[{canonical_addr}]{rest}"

    return netloc


def canonicalize_url(url: str) -> str:
    """Return URL with canonicalized hostname (IPv6 normalized to RFC 5952 form).

    Preserves all other URL components unchanged.
    """
    try:
        parsed = urlparse(url)
        canonical_netloc = canonicalize_hostname(parsed.netloc)
        return urlunparse((
            parsed.scheme,
            canonical_netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        ))
    except Exception:
        # If parsing fails, return original URL
        return url


def is_yggdrasil(addr: str) -> bool:
    """Check if address is in the Yggdrasil range (200::/7).

    Returns True only if addr is an IPv6 address in the Yggdrasil range.
    IPv4 addresses, hostnames, and non-Yggdrasil IPv6 addresses return False.
    """
    try:
        ip = ipaddress.IPv6Address(addr)
        return ip in ipaddress.IPv6Network("200::/7")
    except (ipaddress.AddressValueError, ValueError):
        return False


def extract_hostname(netloc: str) -> str:
    """Extract hostname from netloc, handling IPv6 bracket notation.

    For '[addr]:port' returns 'addr'.
    For 'host:port' returns 'host'.
    For just a host/addr returns it unchanged.
    """
    if not netloc:
        return netloc

    if netloc.startswith("["):
        # IPv6 in brackets
        bracket_end = netloc.find("]")
        if bracket_end != -1:
            return netloc[1:bracket_end]

    # For IPv4 or hostname with port, split on rightmost ':'
    if ":" in netloc:
        return netloc.rsplit(":", 1)[0]

    return netloc


def url_network(url: str) -> str:
    """Classify URL by network type: "mesh" or "clearnet".

    Returns "mesh" if the URL contains a Yggdrasil IPv6 address (200::/7).
    Returns "clearnet" for all other URLs (IPv4, hostnames, non-Yggdrasil IPv6).

    Handles bracket notation correctly for IPv6 addresses.
    """
    try:
        parsed = urlparse(url)
        hostname = extract_hostname(parsed.netloc)
        if is_yggdrasil(hostname):
            return "mesh"
    except Exception:
        pass
    return "clearnet"

"""Rendezvous seed discovery: fetch signed service records and enqueue crawl targets.

Fetches /api/v1/services from a rendezvous server, verifies Ed25519 signatures,
filters for Yggdrasil (mesh) network endpoints, and enqueues matching addresses
to the crawler's queue.

All records must have a valid 'signature' field. Invalid records are logged but
do not halt processing. Missing or unparseable endpoints are silently skipped.
"""

import json
from typing import Optional, Tuple, Dict, List
from urllib.parse import urlparse

import config
from logger import logger
from network import fetch_verified_snapshot
from signature import verify_signature
from url_utils import url_network


def fetch_service_records(
    rendezvous_url: str,
    *,
    timeout: Optional[Tuple[float, float]] = None,
    max_records: int = 10000,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """
    Fetch /api/v1/services from rendezvous server.

    Returns:
        (records_list, error_string) where records_list is list of service dicts
        or None if fetch/parse fails. error_string describes the failure if any.
    """
    api_url = rendezvous_url.rstrip("/") + "/api/v1/services"

    # Use fetch_verified_snapshot to get both content-addressable retrieval
    # and automatic per-network timeout selection
    data, error = fetch_verified_snapshot(api_url, timeout=timeout)

    if error:
        return None, f"Failed to fetch from {api_url}: {error}"

    if not isinstance(data, dict):
        return None, "Rendezvous response is not a JSON object"

    records = data.get("records", [])
    if not isinstance(records, list):
        return None, "Rendezvous 'records' field is not a list"

    if len(records) > max_records:
        return None, f"Too many records ({len(records)} > {max_records})"

    return records, None


def extract_yggdrasil_endpoints(record: dict) -> List[str]:
    """
    Extract Yggdrasil endpoints from a service record.

    Returns:
        List of endpoint addresses (e.g., ["[200:abcd::1]:8080", ...])
        Empty list if record has no yggdrasil endpoints or endpoints are invalid.
    """
    if not isinstance(record, dict):
        return []

    endpoints = record.get("endpoints")
    if not isinstance(endpoints, list):
        return []

    ygg_addrs = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue

        if endpoint.get("network") != "yggdrasil":
            continue

        address = endpoint.get("address")
        if not isinstance(address, str) or not address:
            continue

        # Validate format: must be able to parse as a URL
        # We don't validate the address itself here; that's done by crawler.enqueue_links()
        ygg_addrs.append(address)

    return ygg_addrs


def ingest_rendezvous_seeds(
    crawler,
    rendezvous_url: str,
    *,
    timeout: Optional[Tuple[float, float]] = None,
) -> Dict[str, int]:
    """
    Fetch service records from rendezvous, verify signatures, extract Yggdrasil
    endpoints, and enqueue to crawler.

    Args:
        crawler: Crawler instance with queue and seen attributes.
        rendezvous_url: Base URL of rendezvous server (e.g., "http://[200:...]:8080").
        timeout: Optional override for request timeout tuple.

    Returns:
        Dict with counts: {
            "fetched": number of records fetched,
            "verified": number with valid signatures,
            "enqueued": number of endpoints added to crawler queue,
            "rejected": number of records with invalid signatures,
        }
    """
    records, error = fetch_service_records(rendezvous_url, timeout=timeout)

    if error:
        logger.warning(f"Rendezvous seed discovery failed: {error}")
        return {
            "fetched": 0,
            "verified": 0,
            "enqueued": 0,
            "rejected": 0,
        }

    counts = {
        "fetched": len(records),
        "verified": 0,
        "enqueued": 0,
        "rejected": 0,
    }

    for i, record in enumerate(records):
        if not isinstance(record, dict):
            logger.debug(f"Record {i}: skipping non-dict record")
            counts["rejected"] += 1
            continue

        # Extract operator pubkey for verification
        operator_pubkey = record.get("operator_pubkey")
        if not isinstance(operator_pubkey, str):
            logger.debug(f"Record {i}: missing or invalid operator_pubkey")
            counts["rejected"] += 1
            continue

        # Verify signature
        if not verify_signature(record, operator_pubkey):
            logger.debug(f"Record {i}: signature verification failed")
            counts["rejected"] += 1
            continue

        counts["verified"] += 1

        # Extract yggdrasil endpoints
        endpoints = extract_yggdrasil_endpoints(record)
        for addr in endpoints:
            # Convert address to URL format for crawler
            # If address already has scheme, use as-is; otherwise assume http://
            if "://" in addr:
                url = addr
            else:
                url = f"http://{addr}"

            # Enqueue to crawler
            if url not in crawler.seen:
                crawler.seen.add(url)
                crawler.queue.append(url)
                counts["enqueued"] += 1
                logger.debug(f"Enqueued seed from rendezvous: {url}")

    logger.info(
        f"Rendezvous seed discovery complete: "
        f"fetched={counts['fetched']} "
        f"verified={counts['verified']} "
        f"enqueued={counts['enqueued']} "
        f"rejected={counts['rejected']}"
    )

    return counts

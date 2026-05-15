#!/usr/bin/env python3
"""Step 6: Real-mesh smoke test.

Attempts to contact actual Yggdrasil peers and test rendezvous integration.
Documents connectivity, timeout behavior, and signature verification against
real network conditions.
"""

import sys
import time
import json
from typing import Optional, List, Dict
from urllib.parse import urlparse

from logger import logger
from seeds_rendezvous import fetch_service_records, ingest_rendezvous_seeds
from crawler import Crawler


# Known Yggdrasil peers from environment
MESH_PEERS = [
    # From the getpeers output — these are reachable peers
    "http://[200:c228:5ae8:de9c:9a23:ef10:1f7c:8f2b]:8080",
    "http://[200:b701:4da3:1cc8:3d27:82fa:8102:2db8]:8080",
    "http://[201:9aa8:10cd:192e:1c71:9455:80b9:931f]:8080",
    "http://[202:3a90:7716:a6a7:1230:2ca3:22d3:b49]:8080",
]


def test_peer_connectivity(peer_url: str, timeout: float = 5.0) -> Dict:
    """Test basic TCP connectivity to a peer."""
    import socket

    result = {
        "peer": peer_url,
        "reachable": False,
        "latency_ms": None,
        "error": None,
    }

    parsed = urlparse(peer_url)
    # Extract IPv6 address from brackets
    hostname = parsed.hostname
    port = parsed.port or 8080

    if not hostname:
        result["error"] = "Could not parse hostname"
        return result

    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((hostname, port))
        sock.close()
        elapsed_ms = (time.time() - start) * 1000
        result["reachable"] = True
        result["latency_ms"] = round(elapsed_ms, 2)
    except socket.timeout:
        result["error"] = f"Timeout after {timeout}s"
    except ConnectionRefusedError:
        result["error"] = "Connection refused"
    except socket.gaierror as e:
        result["error"] = f"DNS/address resolution failed: {e}"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def test_rendezvous_fetch(peer_url: str) -> Dict:
    """Test fetching and parsing service records."""
    result = {
        "peer": peer_url,
        "fetched": False,
        "records_count": 0,
        "error": None,
        "sample_record": None,
    }

    try:
        records, error = fetch_service_records(peer_url, timeout=(5.0, 10.0))

        if error:
            result["error"] = error
            return result

        if records is None:
            result["error"] = "Returned None"
            return result

        result["fetched"] = True
        result["records_count"] = len(records)

        if records:
            # Log first record (with signature hidden)
            sample = dict(records[0])
            sample.pop("signature", None)
            result["sample_record"] = sample

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def test_seed_ingestion(peer_url: str) -> Dict:
    """Test full seed ingestion pipeline."""
    result = {
        "peer": peer_url,
        "success": False,
        "counts": None,
        "error": None,
    }

    try:
        crawler = Crawler()
        initial_queue_size = len(crawler.queue)

        counts = ingest_rendezvous_seeds(crawler, peer_url, timeout=(5.0, 10.0))

        result["counts"] = counts
        result["success"] = counts is not None
        result["queue_growth"] = len(crawler.queue) - initial_queue_size

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def run_smoke_test():
    """Run full smoke test against available mesh peers."""
    logger.info("=" * 70)
    logger.info("STEP 6: REAL-MESH SMOKE TEST")
    logger.info("=" * 70)

    results = {
        "timestamp": time.time(),
        "peers_tested": len(MESH_PEERS),
        "peers_reachable": 0,
        "rendezvous_responsive": 0,
        "seeds_enqueued": 0,
        "details": [],
    }

    for peer_url in MESH_PEERS:
        logger.info("")
        logger.info(f"Testing peer: {peer_url}")
        logger.info("-" * 70)

        peer_result = {
            "peer": peer_url,
            "connectivity": None,
            "rendezvous": None,
            "ingestion": None,
        }

        # Phase 1: Connectivity
        logger.info("  Phase 1: Testing connectivity...")
        connectivity = test_peer_connectivity(peer_url)
        peer_result["connectivity"] = connectivity

        if connectivity["reachable"]:
            results["peers_reachable"] += 1
            logger.info(f"    ✓ Reachable (latency: {connectivity['latency_ms']}ms)")

            # Phase 2: Rendezvous fetch
            logger.info("  Phase 2: Fetching rendezvous records...")
            rendezvous = test_rendezvous_fetch(peer_url)
            peer_result["rendezvous"] = rendezvous

            if rendezvous["fetched"]:
                results["rendezvous_responsive"] += 1
                logger.info(
                    f"    ✓ Fetched {rendezvous['records_count']} service records"
                )

                if rendezvous["sample_record"]:
                    logger.info(
                        f"      Sample: {json.dumps(rendezvous['sample_record'], indent=8)}"
                    )

                # Phase 3: Seed ingestion
                logger.info("  Phase 3: Ingesting seeds into crawler queue...")
                ingestion = test_seed_ingestion(peer_url)
                peer_result["ingestion"] = ingestion

                if ingestion["success"]:
                    counts = ingestion["counts"]
                    results["seeds_enqueued"] += counts.get("enqueued", 0)
                    logger.info(
                        f"    ✓ Verified: {counts['verified']}, "
                        f"Enqueued: {counts['enqueued']}, "
                        f"Rejected: {counts['rejected']}"
                    )
                else:
                    logger.warning(
                        f"    ✗ Ingestion failed: {ingestion.get('error')}"
                    )
            else:
                logger.warning(f"    ✗ Rendezvous fetch failed: {rendezvous['error']}")
        else:
            logger.warning(f"    ✗ Not reachable: {connectivity['error']}")

        results["details"].append(peer_result)

    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("SMOKE TEST SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Peers tested:              {results['peers_tested']}")
    logger.info(f"Peers reachable:           {results['peers_reachable']}")
    logger.info(f"Rendezvous responsive:     {results['rendezvous_responsive']}")
    logger.info(f"Total seeds enqueued:      {results['seeds_enqueued']}")
    logger.info("")

    if results["peers_reachable"] == 0:
        logger.warning("No peers were reachable. Possible causes:")
        logger.warning("  - Yggdrasil not running locally")
        logger.warning("  - Peers not accepting connections on port 8080")
        logger.warning("  - No rendezvous servers deployed on mesh yet")
    elif results["rendezvous_responsive"] == 0:
        logger.warning("Peers reachable but no rendezvous service found.")
        logger.warning("  - Services may be on different ports")
        logger.warning("  - Rendezvous servers not yet deployed")
    elif results["seeds_enqueued"] > 0:
        logger.info("✓ SUCCESS: Seeds discovered and enqueued")
        logger.info("  Next: Run crawler to test mesh endpoint reachability")
    else:
        logger.info("Peers and services found, but no Yggdrasil endpoints.")
        logger.info("  This is expected if rendezvous only advertises clearnet services.")

    logger.info("=" * 70)

    return results


if __name__ == "__main__":
    results = run_smoke_test()

    # Write results to file for later analysis
    with open("smoke_test_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Results saved to smoke_test_results.json")

    sys.exit(0 if results["peers_reachable"] > 0 else 1)

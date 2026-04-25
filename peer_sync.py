import json

import config
from logger import logger
from network import fetch_verified_snapshot
from validator import validate_snapshot


def is_peer_snapshot_stale(local_snapshot, peer_snapshot):
    if not local_snapshot:
        return False  # Nothing to compare against

    local_ts = local_snapshot.get("timestamp")
    peer_ts = peer_snapshot.get("timestamp")

    if local_ts is None or peer_ts is None:
        return False  # Don't block on missing metadata

    return peer_ts < local_ts


def _read_local_snapshot_for_staleness(indexer):
    """
    Read local snapshot metadata without clobbering in-memory state.

    Indexer.load_snapshot() mutates indexer.records/index, so avoid calling it
    for the real Indexer during a run. Prefer verifying and reading the on-disk
    snapshot for timestamp gating.
    """
    if hasattr(indexer, "verify_snapshot_files"):
        ok, _error = indexer.verify_snapshot_files()
        if not ok:
            return None
        try:
            with open(config.SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    if hasattr(indexer, "load_snapshot"):
        return indexer.load_snapshot()

    return None


def sync_from_peers(indexer, peer_urls):
    """
    Fetch and merge snapshots from multiple peers.
    """
    local_snapshot = _read_local_snapshot_for_staleness(indexer)

    totals = {
        "peers_total": 0,
        "peers_ok": 0,
        "peers_failed": 0,
        "peers_invalid": 0,
        "added": 0,
        "updated": 0,
        "ignored": 0,
    }

    for peer_url in peer_urls:
        totals["peers_total"] += 1
        logger.info(f"Syncing from peer: {peer_url}")

        peer_data, error = fetch_verified_snapshot(peer_url)
        if error:
            totals["peers_failed"] += 1
            logger.warning(f"Peer fetch failed for {peer_url}: {error}")
            continue

        if not validate_snapshot(peer_data):
            totals["peers_invalid"] += 1
            logger.warning(f"Peer snapshot failed validation for {peer_url}")
            continue

        # Stale Check Gate
        if is_peer_snapshot_stale(local_snapshot, peer_data):
            totals["ignored"] += 1
            logger.warning(f"Skipping stale peer snapshot from {peer_url}")
            continue

        stats = indexer.merge_peer_snapshot(peer_data)
        totals["peers_ok"] += 1
        totals["added"] += stats["added"]
        totals["updated"] += stats["updated"]
        totals["ignored"] += stats["ignored"]

        logger.info(
            f"Peer merge complete for {peer_url}: "
            f"{stats['added']} added, "
            f"{stats['updated']} updated, "
            f"{stats['ignored']} ignored"
        )

    logger.info(
        f"Peer sync summary: "
        f"{totals['peers_ok']}/{totals['peers_total']} peers merged, "
        f"{totals['peers_failed']} failed, "
        f"{totals['peers_invalid']} invalid, "
        f"{totals['added']} added, "
        f"{totals['updated']} updated, "
        f"{totals['ignored']} ignored"
    )

    return totals

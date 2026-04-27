import json
import os
import time

import config
from config import MAX_URLS_PER_RUN

SNAPSHOTS_DIR = config.SNAPSHOTS_DIR
from logger import logger
from crawler import Crawler
from indexer import Indexer
from sandbox import Sandbox
from validator import validate_diff
from peer_sync import sync_from_peers
from ingest import ingest_outbox, ingest_makt_outbox


def phase_load_previous_snapshot(indexer):
    return indexer.load_snapshot()


def phase_local_crawl(indexer, crawler):
    processed = 0

    while processed < MAX_URLS_PER_RUN:
        url = crawler.next_url()
        if url is None:
            break

        content, error = Sandbox.run_isolated(crawler.fetch, url)
        if error:
            logger.warning(f"Skipping {url}: {error}")
            continue

        indexer.add_record(url, content)

        links = crawler.extract_links(content, url)
        crawler.enqueue_links(links)

        processed += 1

    return processed


def phase_log_crawl_status(processed, crawler):
    queue_size = len(getattr(crawler, "queue", []))
    seen_size = len(getattr(crawler, "seen", []))

    logger.info(
        f"Processed {processed} URLs this run; "
        f"queue={queue_size} seen={seen_size}"
    )


def phase_ingest_outbox(indexer, outbox_dir):
    return ingest_outbox(indexer, outbox_dir)


def phase_ingest_makt_outbox(indexer, outbox_dir):
    return ingest_makt_outbox(indexer, outbox_dir)


def phase_peer_sync(indexer, peer_urls):
    if peer_urls:
        sync_from_peers(indexer, peer_urls)


def phase_diff_and_write(indexer, previous_snapshot):
    if previous_snapshot is None:
        logger.info("No previous snapshot available; skipping diff")
        return False

    diff = indexer.diff_against(previous_snapshot)

    if not validate_diff(diff):
        logger.error("Diff schema validation failed; not writing diff.json")
        return False

    logger.info(
        f"Diff summary: "
        f"{len(diff['new'])} new, "
        f"{len(diff['changed'])} changed, "
        f"{len(diff['unchanged'])} unchanged"
    )

    diff_path = os.path.join(SNAPSHOTS_DIR, "diff.json")
    temp_path = diff_path + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(diff, f, indent=2)

    os.replace(temp_path, diff_path)
    return True


def phase_save_and_archive(indexer):
    # save_snapshot() handles archiving internally
    snapshot_hash = indexer.save_snapshot()
    logger.info(f"Snapshot hash: {snapshot_hash}")
    return snapshot_hash


def sync_peers(indexer, peer_urls):
    """
    Ingest peers without running a crawl cycle.

    Thin adapter over sync_from_peers. Maps the internal totals dict
    to the shape cmd_sync expects:

      sync_from_peers keys → sync_peers keys
      peers_total          → attempted
      peers_ok             → accepted
      peers_failed         → counted in rejected
      peers_invalid        → counted in rejected

    'ignored' in the internal totals is a mixed count (stale peer
    snapshots + individual records older than local). It is not
    surfaced as rejected because those are not failures — they are
    correct staleness gates working as intended.
    """
    totals = sync_from_peers(indexer, peer_urls)

    return {
    "attempted":     totals["peers_total"],
    "accepted":      totals["peers_ok"],
    "rejected":      totals["peers_failed"] + totals["peers_invalid"],
    "added":         totals["added"],
    "updated":       totals["updated"],
    "ignored":       totals["ignored"],
    "snapshot_hash": None,
    "details":       [],
}


def _next_backoff_iteration(current_iteration, failures, max_backoff_iterations):
    delay = min(2 ** failures, max_backoff_iterations)
    return current_iteration + delay


def get_node_state(indexer, crawler, iteration=None, peer_failures=None, snapshot_failures=None):
    return {
        "queue_size": len(getattr(crawler, "queue", [])),
        "seen_size": len(getattr(crawler, "seen", [])),
        "index_size": len(getattr(indexer, "index", {})),
        "iteration": iteration,
        "peer_failures": peer_failures,
        "snapshot_failures": snapshot_failures,
    }


def run_once(indexer, crawler, peer_urls):
    previous_snapshot = phase_load_previous_snapshot(indexer)
    processed = phase_local_crawl(indexer, crawler)
    phase_log_crawl_status(processed, crawler)
    phase_ingest_outbox(indexer, getattr(config, "OUTBOX_DIR", "outbox"))
    phase_ingest_makt_outbox(indexer, getattr(config, "MAKT_OUTBOX_DIR", "makt_outbox"))
    phase_peer_sync(indexer, peer_urls)
    diff_written = phase_diff_and_write(indexer, previous_snapshot)
    snapshot_hash = phase_save_and_archive(indexer)

    if not isinstance(snapshot_hash, str) or not snapshot_hash:
        raise RuntimeError("Snapshot hash missing after save")

    state = get_node_state(indexer, crawler)

    return {
        "processed": processed,
        "snapshot_hash": snapshot_hash,
        "diff_written": diff_written,
        "state": state,
    }


def run_loop(
    indexer,
    crawler,
    peer_urls,
    max_runs=None,
    sleep_seconds=5,
    sync_every=5,
    snapshot_every=5,
    max_backoff_iterations=32,
):
    if sync_every < 1 or snapshot_every < 1:
        raise ValueError("Intervals must be >= 1")
    if max_backoff_iterations < 1:
        raise ValueError("max_backoff_iterations must be >= 1")

    iteration = 0

    peer_failures = 0
    snapshot_failures = 0
    peer_next_allowed = 0
    snapshot_next_allowed = 0
    previous_snapshot = None
    snapshot_reader = Indexer()

    # Best-effort: seed the in-memory indexer with the existing local snapshot
    # before starting the crawl loop. Keep this out of the snapshot backoff
    # path so scheduling/order tests can reason about phase execution.
    if hasattr(indexer, "load_snapshot"):
        try:
            indexer.load_snapshot()
        except Exception as exc:
            logger.warning(f"Initial snapshot load failed: {exc}")

    try:
        while True:
            if max_runs is not None and iteration >= max_runs:
                break

            processed = phase_local_crawl(indexer, crawler)
            phase_log_crawl_status(processed, crawler)

            # Debug state exposure
            state = get_node_state(
                indexer,
                crawler,
                iteration=iteration,
                peer_failures=peer_failures,
                snapshot_failures=snapshot_failures,
            )

            logger.debug(
                f"State: iter={state['iteration']} "
                f"queue={state['queue_size']} "
                f"seen={state['seen_size']} "
                f"peer_fail={state['peer_failures']} "
                f"snap_fail={state['snapshot_failures']}"
            )

            peer_due = iteration % sync_every == 0
            peer_allowed = iteration >= peer_next_allowed

            if peer_due and peer_allowed:
                try:
                    phase_peer_sync(indexer, peer_urls)
                    peer_failures = 0
                    peer_next_allowed = iteration
                except Exception as exc:
                    peer_failures += 1
                    peer_next_allowed = _next_backoff_iteration(
                        iteration,
                        peer_failures,
                        max_backoff_iterations,
                    )
                    logger.warning(
                        f"Peer sync failed: {exc}; "
                        f"backing off until iteration {peer_next_allowed}"
                    )

            snapshot_due = iteration % snapshot_every == 0
            snapshot_allowed = iteration >= snapshot_next_allowed

            if snapshot_due and snapshot_allowed:
                try:
                    if previous_snapshot is None:
                        previous_snapshot = phase_load_previous_snapshot(snapshot_reader)
                    phase_diff_and_write(indexer, previous_snapshot)
                    phase_save_and_archive(indexer)
                    # Update baseline for the next diff without re-loading from
                    # disk (which can clobber in-memory crawl/merge state).
                    records = getattr(indexer, "records", None)
                    if isinstance(records, list):
                        previous_snapshot = {
                            "records": [
                                {"url": r.get("url"), "content_hash": r.get("content_hash")}
                                for r in records
                                if isinstance(r, dict)
                                and "url" in r
                                and "content_hash" in r
                            ]
                        }
                    snapshot_failures = 0
                    snapshot_next_allowed = iteration
                except Exception as exc:
                    snapshot_failures += 1
                    snapshot_next_allowed = _next_backoff_iteration(
                        iteration,
                        snapshot_failures,
                        max_backoff_iterations,
                    )
                    logger.warning(
                        f"Snapshot phase failed: {exc}; "
                        f"backing off until iteration {snapshot_next_allowed}"
                    )

            iteration += 1

            if max_runs is not None and iteration >= max_runs:
                break

            time.sleep(sleep_seconds)

    except KeyboardInterrupt:
        logger.info("Continuous run interrupted; shutting down cleanly")


def main(peer_urls=None):
    logger.info("=== YggCrawl Phase 2: Crawl + Verified Peer Merge ===")

    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

    crawler = Crawler()
    indexer = Indexer()

    result = run_once(indexer, crawler, peer_urls)
    
    logger.info(
        f"Run complete: processed={result['processed']} "
        f"snapshot_hash={result['snapshot_hash']} "
        f"diff_written={result['diff_written']} "
        f"queue={result['state']['queue_size']} "
        f"seen={result['state']['seen_size']} "
        f"index={result['state']['index_size']}"
    )

    logger.info("=== Phase 2 Complete ===")


if __name__ == "__main__":
    import config

    main(getattr(config, "PEER_URLS", []))

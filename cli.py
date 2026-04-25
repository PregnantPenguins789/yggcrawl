"""
cli.py — YggCrawl operator shell

Four user-facing surfaces:
  Frontier  → seeds list / seeds add
  Peers     → peers list / peers add
  State     → status / diff / verify
  Control   → run / loop / serve / sync

All business logic lives in main, crawler, indexer, network, validator.
This module is dispatch-only.
"""

import argparse
import json
import os
from pathlib import Path

import config
import main
import network
from ingest import ingest_outbox
import validator
from crawler import Crawler
from indexer import Indexer


DEFAULT_NODE_HOME = Path.home() / ".yggcrawl"


# ---------------------------------------------------------------------------
# Node home resolution and initialization
# ---------------------------------------------------------------------------

def resolve_node_home(explicit_home=None):
    if explicit_home:
        return Path(explicit_home).expanduser().resolve()
    env_home = os.environ.get("YGGCRAWL_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return DEFAULT_NODE_HOME


def ensure_node_home(node_home: Path):
    node_home.mkdir(parents=True, exist_ok=True)
    (node_home / "data").mkdir(parents=True, exist_ok=True)
    (node_home / "data" / "archive").mkdir(parents=True, exist_ok=True)

    for filename, default in [
        ("seeds.txt", ""),
        ("peers.txt", ""),
        ("config.json", "{}\n"),
    ]:
        p = node_home / filename
        if not p.exists():
            p.write_text(default, encoding="utf-8")


def load_lines_file(path: Path):
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def load_node_files(node_home: Path):
    config_path = node_home / "config.json"
    try:
        node_config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid config.json: {exc}") from exc

    return {
        "seeds": load_lines_file(node_home / "seeds.txt"),
        "peers": load_lines_file(node_home / "peers.txt"),
        "config": node_config,
    }


def apply_node_home_to_config(node_home: Path, node_config: dict):
    data_dir = node_home / "data"
    archive_dir = data_dir / "archive"

    config.SNAPSHOTS_DIR = str(data_dir)
    config.ARCHIVE_DIR = str(archive_dir)
    config.SNAPSHOT_FILE = str(data_dir / "current.json")
    config.SNAPSHOT_HASH_FILE = str(data_dir / "current.json.sha256")

    if "node_id" in node_config:
        config.NODE_ID = node_config["node_id"]
    if "max_urls_per_run" in node_config:
        config.MAX_URLS_PER_RUN = node_config["max_urls_per_run"]

    # main caches these at import time; keep it aligned with config so the CLI
    # home directory behaves consistently for diff output and crawl limits.
    main.SNAPSHOTS_DIR = config.SNAPSHOTS_DIR
    main.MAX_URLS_PER_RUN = config.MAX_URLS_PER_RUN


def seed_crawler(crawler: Crawler, seeds):
    if hasattr(crawler, "enqueue_links"):
        crawler.enqueue_links(seeds)
        return
    if hasattr(crawler, "queue"):
        for seed in seeds:
            if seed not in crawler.queue:
                crawler.queue.append(seed)
        return
    raise RuntimeError("Crawler has no supported seeding mechanism")


def _init_node(args):
    """Resolve, create, and apply node home. Returns (node_home, node_files)."""
    node_home = resolve_node_home(args.home)
    ensure_node_home(node_home)
    node_files = load_node_files(node_home)
    apply_node_home_to_config(node_home, node_files["config"])
    return node_home, node_files


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def get_status(indexer: Indexer, crawler: Crawler):
    previous_snapshot = indexer.load_snapshot()
    state = main.get_node_state(indexer, crawler)

    snapshot_hash = None
    if os.path.exists(config.SNAPSHOT_HASH_FILE):
        with open(config.SNAPSHOT_HASH_FILE, "r", encoding="utf-8") as f:
            snapshot_hash = f.read().strip()

    diff_summary = None
    diff_path = Path(config.SNAPSHOTS_DIR) / "diff.json"
    if diff_path.exists():
        try:
            diff_obj = json.loads(diff_path.read_text(encoding="utf-8"))
            diff_summary = {
                "new":       len(diff_obj.get("new", [])),
                "changed":   len(diff_obj.get("changed", [])),
                "unchanged": len(diff_obj.get("unchanged", [])),
            }
        except json.JSONDecodeError:
            pass

    snapshot_timestamp = None
    record_count = 0
    if previous_snapshot:
        snapshot_timestamp = previous_snapshot.get("timestamp")
        record_count = len(previous_snapshot.get("records", []))

    return {
        "node_id":            getattr(config, "NODE_ID", "unknown"),
        "queue_size":         state["queue_size"],
        "seen_size":          state["seen_size"],
        "index_size":         state["index_size"],
        "record_count":       record_count,
        "snapshot_hash":      snapshot_hash,
        "snapshot_timestamp": snapshot_timestamp,
        "diff_summary":       diff_summary,
    }


def print_status(status, seeds, peers):
    print(f"YggCrawl Node: {status['node_id']}")
    print(
        f"Frontier : {len(seeds)} seeds  |  "
        f"queue={status['queue_size']}  seen={status['seen_size']}"
    )
    print(f"Mesh     : {len(peers)} peers configured")

    short_hash = status["snapshot_hash"][:12] if status["snapshot_hash"] else "none"
    print(
        f"Ledger   : {status['record_count']} records  |  "
        f"last hash: {short_hash}"
    )

    ts = status["snapshot_timestamp"] or "none"
    print(f"Timestamp: {ts}")

    if status["diff_summary"] is not None:
        ds = status["diff_summary"]
        print(
            f"Diff     : +{ds['new']} new  "
            f"~{ds['changed']} changed  "
            f"={ds['unchanged']} unchanged"
        )
    else:
        print("Diff     : none")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_run(args):
    _, node_files = _init_node(args)
    crawler = Crawler()
    indexer = Indexer()
    seed_crawler(crawler, node_files["seeds"])

    result = main.run_once(indexer, crawler, node_files["peers"])

    print("Run complete")
    print(f"  Processed     : {result['processed']}")
    print(f"  Snapshot hash : {result['snapshot_hash']}")
    print(f"  Diff written  : {result['diff_written']}")


def cmd_sync(args):
    _, node_files = _init_node(args)

    peers = node_files["peers"]
    if not peers:
        print("No peers configured. Add peers with: yggcrawl peers add <url>")
        return

    indexer = Indexer()
    indexer.load_snapshot()

    outbox = os.environ.get("PYPI_PLACE_OUTBOX")
    if outbox:
        ingest_counts = ingest_outbox(indexer, outbox)
        print(f"Ingest: {ingest_counts['accepted']} accepted, {ingest_counts['rejected']} rejected")

    result = main.sync_peers(indexer, peers)

    ingest_accepted = ingest_counts.get("accepted", 0) if outbox else 0
    if result.get("accepted", 0) > 0 or ingest_accepted > 0:
        snapshot_hash = main.phase_save_and_archive(indexer)
        result["snapshot_hash"] = snapshot_hash

    accepted  = result.get("accepted", 0)
    rejected  = result.get("rejected", 0)
    attempted = result.get("attempted", len(peers))

    print(f"Sync complete  ({attempted} peer{'s' if attempted != 1 else ''} attempted)")
    print(f"  Accepted : {accepted}")
    print(f"  Rejected : {rejected}")
    print(f"  Added    : {result.get('added', 0)}")
    print(f"  Updated  : {result.get('updated', 0)}")
    print(f"  Ignored  : {result.get('ignored', 0)}")

    if result.get("snapshot_hash"):
        print(f"  New hash : {result['snapshot_hash']}")

    if args.verbose and result.get("details"):
        print()
        for entry in result["details"]:
            status = "ok" if entry.get("accepted") else "rejected"
            reason = f"  -- {entry['reason']}" if entry.get("reason") else ""
            print(f"  {entry['peer']:<55} [{status}]{reason}")


def cmd_loop(args):
    _, node_files = _init_node(args)
    crawler = Crawler()
    indexer = Indexer()
    seed_crawler(crawler, node_files["seeds"])

    main.run_loop(
        indexer=indexer,
        crawler=crawler,
        peer_urls=node_files["peers"],
        max_runs=args.max_runs,
        sleep_seconds=args.sleep_seconds,
        sync_every=args.sync_every,
        snapshot_every=args.snapshot_every,
        max_backoff_iterations=args.max_backoff_iterations,
    )


def cmd_serve(args):
    _, node_files = _init_node(args)
    print(f"Serving snapshot on port {args.port} ...")
    network.run_server(port=args.port)


def cmd_status(args):
    _, node_files = _init_node(args)
    crawler = Crawler()
    indexer = Indexer()
    seed_crawler(crawler, node_files["seeds"])

    status = get_status(indexer, crawler)
    print_status(status, node_files["seeds"], node_files["peers"])


def cmd_diff(args):
    node_home, _ = _init_node(args)
    diff_path = Path(config.SNAPSHOTS_DIR) / "diff.json"

    if not diff_path.exists():
        print("No diff.json available")
        return

    diff_obj = json.loads(diff_path.read_text(encoding="utf-8"))

    if args.json:
        print(json.dumps(diff_obj, indent=2))
        return

    print("Latest diff")
    print(f"  New       : {len(diff_obj.get('new', []))}")
    print(f"  Changed   : {len(diff_obj.get('changed', []))}")
    print(f"  Unchanged : {len(diff_obj.get('unchanged', []))}")


def cmd_verify(args):
    node_home, _ = _init_node(args)
    snapshot_path = Path(config.SNAPSHOT_FILE)

    if not snapshot_path.exists():
        print("No snapshot found")
        return

    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Snapshot parse error: {exc}")
        return

    # validator.validate_snapshot returns bool, not a dict
    is_valid = validator.validate_snapshot(snapshot)

    if is_valid:
        print("Snapshot valid")
        if args.verbose:
            print(f"  Records   : {len(snapshot.get('records', []))}")
            print(f"  Timestamp : {snapshot.get('timestamp', 'none')}")
    else:
        print("Snapshot INVALID")


# ---------------------------------------------------------------------------
# File mutation helpers
# ---------------------------------------------------------------------------

def _looks_like_url(value: str) -> bool:
    """
    Minimal URL check — must start with http:// or https://.
    Accepts IPv6 bracket notation in the host position.
    Not a full RFC 3986 parser; purpose is catching obvious operator errors
    before they pollute seeds.txt or peers.txt.
    """
    return value.startswith("http://") or value.startswith("https://")


def append_entry(path: Path, value: str) -> str:
    """
    Append value to path if not already present.

    Returns one of:
      "added"      — entry written
      "duplicate"  — entry already present, file unchanged
    """
    existing = load_lines_file(path)
    if value in existing:
        return "duplicate"
    with path.open("a", encoding="utf-8") as f:
        f.write(value + "\n")
    return "added"


def cmd_seeds(args):
    _, node_files = _init_node(args)

    if args.seeds_command == "list":
        seeds = node_files["seeds"]
        if not seeds:
            print("No seeds configured")
            return
        for s in seeds:
            print(s)

    elif args.seeds_command == "add":
        url = args.url.strip()
        if not _looks_like_url(url):
            print(f"Invalid seed URL (must start with http:// or https://): {url}")
            return
        node_home = resolve_node_home(args.home)
        result = append_entry(node_home / "seeds.txt", url)
        if result == "added":
            print(f"Added seed: {url}")
        else:
            print(f"Already present: {url}")

    else:
        args.seeds_parser.print_help()


def cmd_peers(args):
    _, node_files = _init_node(args)

    if args.peers_command == "list":
        peers = node_files["peers"]
        if not peers:
            print("No peers configured")
            return
        for p in peers:
            print(p)

    elif args.peers_command == "add":
        url = args.url.strip()
        if not _looks_like_url(url):
            print(f"Invalid peer URL (must start with http:// or https://): {url}")
            return
        node_home = resolve_node_home(args.home)
        result = append_entry(node_home / "peers.txt", url)
        if result == "added":
            print(f"Added peer: {url}")
        else:
            print(f"Already present: {url}")

    else:
        args.peers_parser.print_help()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="yggcrawl",
        description="Sovereign index node for the Yggdrasil mesh",
    )
    parser.add_argument("--home", metavar="DIR", help="Node home directory")
    subs = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subs.add_parser("run", help="Run one crawl + sync cycle")
    p_run.set_defaults(func=cmd_run)

    # sync
    p_sync = subs.add_parser("sync", help="Ingest peers without crawling")
    p_sync.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-peer outcome")
    p_sync.set_defaults(func=cmd_sync)

    # loop
    p_loop = subs.add_parser("loop", help="Run continuously")
    p_loop.add_argument("--max-runs",               type=int, default=None)
    p_loop.add_argument("--sleep-seconds",           type=int, default=5)
    p_loop.add_argument("--sync-every",              type=int, default=5)
    p_loop.add_argument("--snapshot-every",          type=int, default=5)
    p_loop.add_argument("--max-backoff-iterations",  type=int, default=32)
    p_loop.set_defaults(func=cmd_loop)

    # serve
    p_serve = subs.add_parser("serve", help="Serve snapshot over HTTP")
    p_serve.add_argument("--port", type=int, default=8080)
    p_serve.set_defaults(func=cmd_serve)

    # status
    p_status = subs.add_parser("status", help="Show node state summary")
    p_status.set_defaults(func=cmd_status)

    # diff
    p_diff = subs.add_parser("diff", help="Show latest diff summary")
    p_diff.add_argument("--json", action="store_true", help="Print full diff as JSON")
    p_diff.set_defaults(func=cmd_diff)

    # verify
    p_verify = subs.add_parser("verify", help="Validate snapshot integrity")
    p_verify.add_argument("--verbose", "-v", action="store_true")
    p_verify.set_defaults(func=cmd_verify)

    # seeds
    p_seeds = subs.add_parser("seeds", help="Manage frontier seeds")
    p_seeds.set_defaults(seeds_parser=p_seeds)
    seeds_subs = p_seeds.add_subparsers(dest="seeds_command")
    seeds_subs.add_parser("list", help="List configured seeds")
    p_seeds_add = seeds_subs.add_parser("add", help="Add a seed URL")
    p_seeds_add.add_argument("url", help="URL to add (http:// or https://)")
    p_seeds.set_defaults(func=cmd_seeds, seeds_command=None)

    # peers
    p_peers = subs.add_parser("peers", help="Manage peer list")
    p_peers.set_defaults(peers_parser=p_peers)
    peers_subs = p_peers.add_subparsers(dest="peers_command")
    peers_subs.add_parser("list", help="List configured peers")
    p_peers_add = peers_subs.add_parser("add", help="Add a peer URL")
    p_peers_add.add_argument("url", help="Peer snapshot URL (http:// or https://)")
    p_peers.set_defaults(func=cmd_peers, peers_command=None)

    return parser


def main_cli():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main_cli()

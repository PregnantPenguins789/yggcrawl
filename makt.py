"""
makt.py — Mesh Aware Knowledge Terminal

User-facing CLI for discovering, pulling, verifying, and contributing
LoRA adapters over the Yggdrasil mesh.

Commands:
  makt search <domain>          Search the index for adapters matching domain
  makt list                     List all known adapters in the local index
  makt pull <url>               Pull an adapter from a mesh node and verify hash
  makt verify <name>            Verify a locally stored adapter against its hash
  makt contribute <file>        Announce a local adapter to the mesh via outbox
  makt peers list               List configured MAKT peers
  makt peers add <url>          Add a peer node URL
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

import config
from indexer import Indexer
from logger import logger
from validator import validate_makt_record

MAKT_STORE = Path(getattr(config, "LORA_STORE_DIR", "lora_store"))
MAKT_OUTBOX = Path(getattr(config, "MAKT_OUTBOX_DIR", "makt_outbox"))
MAKT_PEERS_FILE = Path(getattr(config, "MAKT_PEERS_FILE", "makt_peers.txt"))
FETCH_TIMEOUT = 30
MAX_ADAPTER_BYTES = 500_000_000  # 500 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_index():
    indexer = Indexer()
    indexer.load_snapshot()
    return indexer


def _makt_records(indexer):
    return [
        r for r in indexer.records
        if r.get("record_type") in ("lora_adapter", "dataset", "model")
    ]


def _load_peers():
    if not MAKT_PEERS_FILE.exists():
        return []
    lines = []
    for raw in MAKT_PEERS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def _fetch_bytes(url, max_bytes=MAX_ADAPTER_BYTES):
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"Response exceeds {max_bytes} bytes")
    return data


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_search(args):
    indexer = _load_index()
    records = _makt_records(indexer)

    term = args.domain.lower()
    matches = [
        r for r in records
        if term in r.get("domain", "").lower()
        or term in r.get("url", "").lower()
        or term in r.get("base_model", "").lower()
    ]

    if not matches:
        print(f"No adapters found matching '{args.domain}'")
        return

    print(f"Found {len(matches)} adapter(s) matching '{args.domain}':\n")
    for r in matches:
        size_mb = r.get("size_bytes", 0) / 1_000_000
        print(f"  {r.get('domain', 'unknown'):<20} {r.get('base_model', 'unknown'):<20} {size_mb:.1f} MB")
        print(f"    url  : {r['url']}")
        print(f"    hash : {r['content_hash'][:16]}...")
        if r.get("contributed_by"):
            print(f"    from : {r['contributed_by']}")
        print()


def cmd_list(args):
    indexer = _load_index()
    records = _makt_records(indexer)

    if not records:
        print("No MAKT records in local index.")
        return

    print(f"{'DOMAIN':<20} {'BASE MODEL':<22} {'TYPE':<14} {'SIZE':>8}  URL")
    print("-" * 90)
    for r in sorted(records, key=lambda x: x.get("domain", "")):
        size_mb = r.get("size_bytes", 0) / 1_000_000
        print(
            f"  {r.get('domain','?'):<18} "
            f"{r.get('base_model','?'):<20} "
            f"{r.get('record_type','?'):<14} "
            f"{size_mb:>6.1f}MB  "
            f"{r['url']}"
        )


def cmd_pull(args):
    url = args.url.rstrip("/")

    # Derive name from URL
    name = url.split("/")[-1]
    if name.endswith(".bin"):
        name = name[:-4]

    bin_url = url if url.endswith(".bin") else f"{url}.bin"
    hash_url = bin_url[:-4] + ".sha256"

    print(f"Fetching hash from {hash_url} ...")
    try:
        expected_hash = _fetch_bytes(hash_url, max_bytes=256).decode("utf-8").strip()
    except Exception as e:
        print(f"Failed to fetch hash: {e}")
        sys.exit(1)

    print(f"Fetching adapter from {bin_url} ...")
    try:
        data = _fetch_bytes(bin_url)
    except Exception as e:
        print(f"Failed to fetch adapter: {e}")
        sys.exit(1)

    actual_hash = _sha256_bytes(data)
    if actual_hash != expected_hash:
        print(f"Hash mismatch — adapter rejected.")
        print(f"  Expected : {expected_hash}")
        print(f"  Got      : {actual_hash}")
        sys.exit(1)

    MAKT_STORE.mkdir(parents=True, exist_ok=True)
    bin_path = MAKT_STORE / f"{name}.bin"
    hash_path = MAKT_STORE / f"{name}.sha256"

    bin_path.write_bytes(data)
    hash_path.write_text(actual_hash, encoding="utf-8")

    print(f"Verified and saved:")
    print(f"  {bin_path}")
    print(f"  hash: {actual_hash[:16]}...")


def cmd_verify(args):
    name = args.name
    if name.endswith(".bin"):
        name = name[:-4]

    bin_path = MAKT_STORE / f"{name}.bin"
    hash_path = MAKT_STORE / f"{name}.sha256"

    if not bin_path.exists():
        print(f"Adapter not found: {bin_path}")
        sys.exit(1)

    if not hash_path.exists():
        print(f"Hash file not found: {hash_path}")
        sys.exit(1)

    expected = hash_path.read_text(encoding="utf-8").strip()
    print(f"Verifying {name} ...")
    actual = _sha256_file(bin_path)

    if actual == expected:
        print(f"OK — hash verified: {actual[:16]}...")
    else:
        print(f"FAIL — hash mismatch")
        print(f"  Expected : {expected}")
        print(f"  Got      : {actual}")
        sys.exit(1)


def cmd_contribute(args):
    adapter_path = Path(args.file)
    if not adapter_path.exists():
        print(f"File not found: {adapter_path}")
        sys.exit(1)

    if not args.domain:
        print("--domain is required")
        sys.exit(1)

    if not args.base_model:
        print("--base-model is required")
        sys.exit(1)

    print(f"Hashing {adapter_path} ...")
    content_hash = _sha256_file(adapter_path)
    size_bytes = adapter_path.stat().st_size

    # Copy into lora_store so the server can serve it
    MAKT_STORE.mkdir(parents=True, exist_ok=True)
    name = adapter_path.stem
    dest_bin = MAKT_STORE / f"{name}.bin"
    dest_hash = MAKT_STORE / f"{name}.sha256"

    shutil.copy2(adapter_path, dest_bin)
    dest_hash.write_text(content_hash, encoding="utf-8")

    node_id = getattr(config, "NODE_ID", "node-local")
    record = {
        "url": f"ygg://local/lora/{name}",
        "record_type": "lora_adapter",
        "domain": args.domain,
        "base_model": args.base_model,
        "size_bytes": size_bytes,
        "content_hash": content_hash,
        "contributed_by": node_id,
        "fetched_at": int(__import__("time").time()),
    }

    if not validate_makt_record(record):
        print("Record failed validation — check domain and base_model values.")
        sys.exit(1)

    MAKT_OUTBOX.mkdir(parents=True, exist_ok=True)
    outbox_file = MAKT_OUTBOX / f"{name}.json"
    outbox_file.write_text(json.dumps(record, indent=2), encoding="utf-8")

    print(f"Adapter staged for contribution:")
    print(f"  store  : {dest_bin}")
    print(f"  hash   : {content_hash[:16]}...")
    print(f"  record : {outbox_file}")
    print(f"\nRun 'yggcrawl run' to ingest and broadcast.")


def cmd_peers(args):
    if args.peers_command == "list":
        peers = _load_peers()
        if not peers:
            print("No MAKT peers configured.")
            return
        for p in peers:
            print(p)

    elif args.peers_command == "add":
        url = args.url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            print(f"Invalid URL (must start with http:// or https://): {url}")
            sys.exit(1)
        MAKT_PEERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = _load_peers()
        if url in existing:
            print(f"Already present: {url}")
        else:
            with MAKT_PEERS_FILE.open("a", encoding="utf-8") as f:
                f.write(url + "\n")
            print(f"Added peer: {url}")

    else:
        args.peers_parser.print_help()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="makt",
        description="Mesh Aware Knowledge Terminal — pull and share model tunings over Yggdrasil",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # search
    p_search = subs.add_parser("search", help="Search index for adapters by domain")
    p_search.add_argument("domain", help="Domain to search (e.g. plumbing, forestry)")
    p_search.set_defaults(func=cmd_search)

    # list
    p_list = subs.add_parser("list", help="List all known adapters")
    p_list.set_defaults(func=cmd_list)

    # pull
    p_pull = subs.add_parser("pull", help="Pull an adapter from a mesh node")
    p_pull.add_argument("url", help="URL of the adapter (ygg:// or http://[addr]:8080/lora/name)")
    p_pull.set_defaults(func=cmd_pull)

    # verify
    p_verify = subs.add_parser("verify", help="Verify a locally stored adapter")
    p_verify.add_argument("name", help="Adapter name (with or without .bin)")
    p_verify.set_defaults(func=cmd_verify)

    # contribute
    p_contribute = subs.add_parser("contribute", help="Stage a local adapter for mesh broadcast")
    p_contribute.add_argument("file", help="Path to the .bin adapter file")
    p_contribute.add_argument("--domain", required=True, help="Knowledge domain (e.g. plumbing)")
    p_contribute.add_argument("--base-model", required=True, dest="base_model",
                               help="Base model identifier (e.g. mistral-7b-q4)")
    p_contribute.set_defaults(func=cmd_contribute)

    # peers
    p_peers = subs.add_parser("peers", help="Manage MAKT peer nodes")
    p_peers.set_defaults(peers_parser=p_peers)
    peers_subs = p_peers.add_subparsers(dest="peers_command")
    peers_subs.add_parser("list", help="List configured peers")
    p_peers_add = peers_subs.add_parser("add", help="Add a peer node URL")
    p_peers_add.add_argument("url", help="Peer node URL")
    p_peers.set_defaults(func=cmd_peers, peers_command=None)

    return parser


def main_cli():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main_cli()

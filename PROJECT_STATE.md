# PROJECT: YggCrawl + PyPI Place (Integrated Node)

## Core Idea

A **self-sufficient, deterministic data-producing node** that:

1. **Generates structured knowledge locally** (crawl + PyPI testing)
2. **Materializes verifiable artifacts** (snapshots + hashes)
3. **Distributes state over Yggdrasil (mesh network)** instead of relying on clearnet
4. **Converges with peers** via validated snapshot exchange

This is not a service.
It is a **replicating data organism** whose outputs can be independently verified and merged.

---

# ARCHITECTURAL PRINCIPLE

### Artifact > Process

The system does not care if a process is running.

It cares whether this exists:

* `current.json`
* `current.json.sha256`
* (optional) `diff.json`
* archived snapshots

Everything else is just a means to produce those artifacts.

---

# SYSTEM COMPONENTS

## 1. YggCrawl (Core Node)

Responsibilities:

* Crawl sources (bounded, deterministic)
* Maintain index of records:

  ```json
  {
    "url": "...",
    "fetched_at": ...,
    "content_hash": "..."
  }
  ```
* Generate:

  * snapshot (`current.json`)
  * hash (`.sha256`)
  * diff (`diff.json`)
* Validate all data before accepting it
* Merge peer snapshots deterministically

Key properties:

* Order-independent convergence
* Hash-before-parse security model
* Schema validation before merge
* Offline-first operation

---

## 2. PyPI Place (Data Generator)

Responsibilities:

* Execute controlled test environments (Python versions, distros)
* Evaluate packages
* Emit **result records** into an outbox:

Example:

```json
{
  "package": "example",
  "version": "1.2.3",
  "environment": "py3.12-ubuntu",
  "result": "PASS",
  "observed_at": 1710000000
}
```

These are:

* deterministic
* reproducible
* high-value (real compatibility data)

---

## 3. Ingestion Layer (Bridge)

`ingest_outbox(indexer, outbox_dir)`

Responsibilities:

* Read PyPI Place output
* Validate schema
* Convert → YggCrawl record format
* Merge into index
* Move files:

  * `processed/`
  * `rejected/`

This is the **interface between compute-heavy testing and lightweight node state**.

---

## 4. Network Layer (Yggdrasil Distribution)

### Current capability:

* IPv6 HTTP server
* Serves:

  * `/current.json`
  * `/current.json.sha256`

### Model:

* Nodes fetch from peers
* Verify hash
* Validate schema
* Merge deterministically

No trust required.

---

## 5. Control Plane (Execution Model)

Refactored into explicit phases:

```
run_once():
  load_previous_snapshot
  local_crawl
  ingest_outbox        ← NEW
  peer_sync (optional)
  diff_generation
  snapshot_write
  archive
```

Then:

```
run_loop():
  repeat run_once()
  apply scheduling + backoff
```

---

# CURRENT STATE (May 2026)

### Baseline Status: STABLE ✓

**All 89 tests passing.** End-to-end pipeline verified (crawl → ingest → snapshot → diff → hash).

### What is working

* Deterministic snapshot generation ✓
* Hash verification system ✓
* Diff generation + validation ✓
* Archive system ✓
* Peer sync model (logic complete, tested) ✓
* Test suite (89 tests, all passing) ✓
* Outbox production from PyPI Place (confirmed working) ✓
* Ingestion pipeline (PyPI Place → crawler records) ✓
* Network server (exception handling hardened, no empty replies) ✓
* CLI + operator surface ✓
* Loop scheduling with backoff ✓

### What is NOT implemented (reserved for rendezvous integration)

* Yggdrasil-native address handling (200::/7 range, [ipv6]:port syntax)
* Mesh-specific timeouts (currently clearnet-optimized)
* RFC 8785 canonical JSON + Ed25519 signature verification
* Rendezvous seed source consumption
* Service discovery feedback (unpublished services found by crawler)

---

# TARGET DEPLOYMENT (HETZNER CX22)

## Goal

A **continuously running node** on Hetzner cx22 that:

1. Produces data (crawl + PyPI Place ingestion)
2. Publishes signed snapshots
3. Serves them over Yggdrasil
4. Emits a **beacon signal of state**

---

# BEACON CONCEPT (CRITICAL ADDITION)

## Purpose

Provide **observable proof of life and state** over a non-clearnet channel.

## Minimal Beacon Payload

```
node_id
timestamp
snapshot_hash
record_count
last_run_status
```

Example:

```
node-local
1710000000
a94f...e91c
1243
OK
```

## Transmission Options (simple → robust)

1. **Log-based (initial)**

   * Print to terminal connected to Yggdrasil session
   * Visible via SSH / tmux on mesh

2. **HTTP endpoint**

   * `/beacon.txt`
   * Lightweight status check

3. **Push to peer(s)**

   * POST or append-only feed

4. **Gossip-style (future)**

   * Peers relay beacon summaries

---

# ORACLE NODE PROCESS MODEL

Single machine runs:

### Loop (authoritative node)

```
while true:
  run_once()

  if iteration % sync_every == 0:
      sync_from_peers()

  if iteration % snapshot_every == 0:
      write_snapshot()

  emit_beacon()

  sleep(N)
```

### Parallel (optional)

* PyPI Place runs independently
* Writes into outbox
* YggCrawl ingests next cycle

---

# DESIGN STRENGTHS

* Fully auditable pipeline
* Deterministic outputs
* No dependency on external APIs at runtime
* Mesh-native distribution
* Separation of:

  * data production
  * data validation
  * data distribution

---

# NEXT IMPLEMENTATION STEPS: RENDEZVOUS INTEGRATION (ORDERED)

Baseline is stable (89/89 tests passing). Proceeding with Mesh Service Rendezvous Protocol integration.

## 1. Hash format alignment

* Update hash representation from `<hex>` to `sha256:<hex>` (prefix format per rendezvous spec)
* Verify all 89 tests still pass
* Single commit: `align hash format to mesh-rendezvous spec`

## 2. IPv6-literal URL handling verification

* Confirm `crawler.py` correctly handles `http://[200:abcd::1]:8080/path` syntax
* Add unit tests for both IPv4 `example.com:port` and IPv6 bracket forms
* No mesh required; verifies URL parsing layer

## 3. Per-network timeout configuration

* Split `REQUEST_TIMEOUT` into `CLEARNET_TIMEOUT` (10s) and `MESH_TIMEOUT` (30s)
* Classify URLs by address type (200::/7 literals → mesh timeout)
* Plumb through crawler

## 4. Signature verification module

* New `signature.py`: RFC 8785 canonicalization + Ed25519 verification
* Test against RFC 8032 test vectors (canonical, not synthetic)
* Test against RFC 8785 canonicalization fixtures
* No integration with crawler yet — isolated primitive

## 5. Rendezvous seed adapter

* New `seeds_rendezvous.py`: fetch from `/api/v1/services`, verify signatures, filter by network
* Convert rendezvous records to crawler seed format
* Tests against mock HTTP server with fixture responses

## 6. First real-mesh smoke test

* Target: confirmed reachable Yggdrasil peer
* Fallback peer identified in advance
* Full log capture and documentation
* Milestone: proof that YggCrawl actually reaches and crawls mesh peers

## 7. Discovery feedback (Role 2)

* Compare crawler findings against rendezvous-known services
* Emit unpublished-discovery records to separate outbox
* Human review before publication

## 8. Beacon emission

* Implement `emit_beacon()` to signal node liveness
* Expose via stdout and `/beacon.txt` endpoint
* Include snapshot hash and timestamp

## 9. Deploy to Hetzner cx22

* Configure Yggdrasil on instance
* Port 8080 reachable via mesh
* Long-running loop (systemd service)
* PyPI Place integration running in parallel

## 10. Verify from second node

* Fetch snapshot from cx22 node via mesh address
* Verify hash matches
* Observe beacon signal
* Confirm end-to-end integrity

---

# WHAT THIS PROVES (POC)

If working, this demonstrates:

* A node can **produce meaningful data continuously**
* That data can be **verified independently**
* It can be **distributed without clearnet dependency**
* Its state can be **observed externally via mesh-native signaling**

That is the foundation for:

* distributed research systems
* resilient archival networks
* trust-minimized data sharing

Read PROJECT_STATE.md and follow it strictly.

Task 1:
Fix network.py so the HTTP handler never re-raises after beginning request handling.
On exception:
- log the exception
- return send_error(500, ...)
- do not leave the client with an empty reply

Also remove duplicate log_message definitions if present.

Task 2:
Inspect main.py and wire ingest_outbox(indexer, outbox_dir) into run_once() in the correct phase after local crawl and before peer sync.

Task 3:
Inspect ingest.py and align PyPI record validation with the actual emitted field name from PyPI Place.
Do not guess: verify whether the emitter writes "result" or "status" and make ingest.py match.

Task 4:
Do not refactor unrelated files.
Do not add dependencies.
Show diffs before broad changes.
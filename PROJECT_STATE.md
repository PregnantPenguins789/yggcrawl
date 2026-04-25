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

# CURRENT STATE (END OF SESSION)

### What is working

* Deterministic snapshot generation
* Hash verification system
* Diff generation + validation
* Archive system
* Peer sync model (logic complete)
* Test suite (broad, includes edge cases)
* Outbox production from PyPI Place (confirmed working)
* Ingestion design (partially implemented, needs cleanup)
* CLI + operator surface exists

### What is partially complete

* `ingest.py` (needs cleanup + full validation path)
* Loop scheduling (exists, needs tuning knobs)
* Backoff logic (implemented, still being stabilized via tests)
* Network server (functional but debugging instability: empty reply / port reuse)

### Known issues

* Test failures:

  * missing config attributes (`SEED_URLS`)
  * import errors (`random` not imported)
* Network instability:

  * stale server processes
  * handler likely failing before response
* Some modules still too tightly coupled (config vs import patterns)

---

# TARGET DEPLOYMENT (ORACLE FREE TIER NODE)

## Goal

A **continuously running node** that:

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

# NEXT IMPLEMENTATION STEPS (ORDERED)

## 1. Stabilize ingestion

* Fix `ingest.py`
* Enforce strict schema validation
* Ensure idempotency

## 2. Fix test suite

* Resolve config import issues
* Fix missing imports
* Ensure green baseline

## 3. Harden network server

* Ensure handler always returns response
* Add explicit exception logging
* Kill stale processes on restart

## 4. Add beacon emission

* Implement `emit_beacon()`
* Attach to loop
* Expose via:

  * stdout
  * `/beacon.txt`

## 5. Deploy to Oracle

* Single VPS node
* Yggdrasil running
* Port 8080 reachable via mesh
* Long-running loop (systemd or tmux)

## 6. Verify from second node

* Fetch snapshot
* Verify hash
* Observe beacon
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
# Local Fixture Testing Plan (No Yggdrasil Required)

**Goal:** Validate rendezvous seed discovery pipeline locally before cloud deployment.

**Requirements:**
- Python 3.10+
- cryptography, rfc8785, pytest (in requirements.txt)
- No Yggdrasil needed
- No network connectivity needed

---

## What Gets Tested

### 1. Fixture Server
- Generates properly signed Ed25519 service records
- Serves via HTTP `/api/v1/services` endpoint
- Mixed endpoints (Yggdrasil + clearnet)

### 2. Signature Verification
- RFC 8785 canonical JSON canonicalization
- Ed25519 signature verification
- Invalid signature rejection

### 3. Endpoint Filtering
- Yggdrasil endpoints extracted (network == "yggdrasil")
- Clearnet/Tor/other endpoints filtered out
- Malformed endpoints skipped gracefully

### 4. Crawler Integration
- Seeds enqueued to crawler.queue
- No duplicates (uses crawler.seen)
- URL formatting correct

### 5. Full Pipeline
- Fetch from fixture server
- Verify all signatures
- Filter all endpoints
- Enqueue all yggdrasil seeds
- Verify crawler state

---

## Running the Tests

### Step 1: Install Dependencies

```bash
cd ~/yggcrawl
pip3 install -r requirements.txt
```

### Step 2: Run Local Tests

```bash
python3 -m pytest tests/test_rendezvous_local.py -v
```

Expected output:
```
test_rendezvous_local.py::TestFixtureServer::test_fixture_imports PASSED
test_rendezvous_local.py::TestFixtureServer::test_fixture_records_are_signed PASSED
test_rendezvous_local.py::TestRendezvousAdapterWithFixture::test_fetch_fixture_records PASSED
test_rendezvous_local.py::TestRendezvousAdapterWithFixture::test_signature_verification_pipeline PASSED
test_rendezvous_local.py::TestRendezvousAdapterWithFixture::test_endpoint_filtering PASSED
test_rendezvous_local.py::TestRendezvousAdapterWithFixture::test_ingest_pipeline_simulation PASSED
test_rendezvous_local.py::TestRendezvousLocalIntegration::test_fixture_server_startup PASSED
test_rendezvous_local.py::TestRendezvousLocalIntegration::test_full_local_pipeline PASSED

====== 8 passed in X.XXs ======
```

### Step 3: Run All Tests (Regression)

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Should show: **200 tests passing** (178 original + 22 rendezvous + 8 local fixture)

### Step 4: Manual Fixture Server Test

```bash
# Terminal 1: Start fixture server
python3 fixture_rendezvous_server.py &

# Terminal 2: Test endpoint
sleep 1
curl http://127.0.0.1:9999/api/v1/services | python3 -m json.tool
```

Expected:
```json
{
  "records": [
    {
      "version": 1,
      "operator_pubkey": "ed25519:...",
      "service_type": "dictd",
      "endpoints": [...],
      "signature": "..."
    },
    ...
  ]
}
```

### Step 5: Manual Adapter Test

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '.')

from fixture_rendezvous_server import FixtureHandler
from seeds_rendezvous import ingest_rendezvous_seeds
from http.server import HTTPServer
from collections import deque
import threading
import time

class MockCrawler:
    def __init__(self):
        self.queue = deque()
        self.seen = set()

# Start server
server = HTTPServer(("127.0.0.1", 9998), FixtureHandler)
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
time.sleep(0.5)

# Test adapter
crawler = MockCrawler()
counts = ingest_rendezvous_seeds(crawler, "http://127.0.0.1:9998", timeout=(2.0, 5.0))

print(f"Results:")
print(f"  Fetched: {counts['fetched']}")
print(f"  Verified: {counts['verified']}")
print(f"  Enqueued: {counts['enqueued']}")
print(f"  Rejected: {counts['rejected']}")
print(f"Crawler queue size: {len(crawler.queue)}")
print(f"URLs enqueued:")
for url in list(crawler.queue):
    print(f"  - {url}")

server.shutdown()
EOF
```

Expected output:
```
Results:
  Fetched: 4
  Verified: 4
  Enqueued: 3
  Rejected: 0
Crawler queue size: 3
URLs enqueued:
  - http://[200:1111:2222:3333::1]:8080
  - http://[200:aaaa:bbbb:cccc::2]:9000
  - http://[200:feed:face:cafe::3]:3000
```

---

## What Each Test Validates

| Test | Validates |
|------|-----------|
| `test_fixture_imports` | Fixture server module loads |
| `test_fixture_records_are_signed` | All 4 test records have valid signatures |
| `test_fixture_has_mixed_endpoints` | Records include both yggdrasil and non-yggdrasil |
| `test_fetch_fixture_records` | Adapter fetches from fixture, parses JSON |
| `test_signature_verification_pipeline` | All signatures verify correctly |
| `test_endpoint_filtering` | Only yggdrasil endpoints extracted |
| `test_ingest_pipeline_simulation` | Full pipeline (fetch→verify→filter→enqueue) |
| `test_fixture_server_startup` | Server starts and serves records |
| `test_full_local_pipeline` | Complete integration: server + adapter |

---

## Test Fixture Breakdown

**Record 1: Single Yggdrasil Endpoint**
```json
{
  "service_type": "dictd",
  "endpoints": [{"network": "yggdrasil", "address": "[200:1111::1]:8080"}]
}
```
→ Should enqueue 1 URL

**Record 2: Mixed Endpoints**
```json
{
  "service_type": "web-server",
  "endpoints": [
    {"network": "yggdrasil", "address": "[200:aaaa::2]:9000"},
    {"network": "clearnet", "address": "example.com:8080"},
    {"network": "tor", "address": "something.onion:8080"}
  ]
}
```
→ Should enqueue 1 URL (filter out 2 non-yggdrasil)

**Record 3: Clearnet Only**
```json
{
  "service_type": "api",
  "endpoints": [{"network": "clearnet", "address": "api.example.com:443"}]
}
```
→ Should enqueue 0 URLs

**Record 4: Another Yggdrasil**
```json
{
  "service_type": "git-server",
  "endpoints": [{"network": "yggdrasil", "address": "[200:feed::3]:3000"}]
}
```
→ Should enqueue 1 URL

**Expected Totals:**
- Fetched: 4 records
- Verified: 4 (all signatures valid)
- Enqueued: 3 (only yggdrasil endpoints)
- Rejected: 0

---

## Success Criteria

✓ All 8 local tests pass  
✓ Fixture server starts and serves valid records  
✓ Adapter fetches, verifies, filters correctly  
✓ Crawler queue contains exactly the right URLs  
✓ No regressions (200 total tests passing)  

---

## If Tests Fail

1. **Fixture import error** → `pip3 install -r requirements.txt`
2. **Signature verification fails** → rfc8785 version issue, check `pip3 show rfc8785`
3. **Server won't start** → Port already in use, kill: `lsof -i :9999`
4. **Timeout errors** → Increase timeout in test (server might be slow)

---

## Next Steps (After Tests Pass)

Once all local tests pass:

1. **Document results** — Save test output for cloud deployment reference
2. **Prepare cloud setup** — Bake yggcrawl + sloklaw + pypiplace into Google Cloud image
3. **Deploy to cloud** — Boot instance with full stack
4. **Validate mesh integration** — Connect to mail server, test cross-machine seed discovery
5. **Monitor production** — Track crawl progress and peer sync

---

## Files

- `fixture_rendezvous_server.py` — Generates and serves signed test records
- `tests/test_rendezvous_local.py` — All validation tests
- `seeds_rendezvous.py` — Production adapter (being tested)
- `signature.py` — Production crypto (being tested)

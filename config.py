SEED_URLS = [
    "http://example.com",
]

PEER_URLS = []

MAX_URLS_PER_RUN = 10

SNAPSHOTS_DIR = "snapshots"
ARCHIVE_DIR = f"{SNAPSHOTS_DIR}/archive"

SNAPSHOT_FILE = f"{SNAPSHOTS_DIR}/current.json"
SNAPSHOT_HASH_FILE = f"{SNAPSHOTS_DIR}/current.json.sha256"

LOG_FILE = "yggcrawl.log"

OUTBOX_DIR = "outbox"

NODE_ID = "node-local"
SCHEMA_VERSION = 1

REQUEST_DELAY = 1.0
REQUEST_TIMEOUT = 10
MAX_RESPONSE_BYTES = 10_000_000  # 10 MB
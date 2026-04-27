import logging

logger = logging.getLogger(__name__)

def validate_snapshot(snapshot: dict) -> bool:
    """Checks if a snapshot dictionary meets the YggCrawl schema."""
    required_keys = {"node_id", "schema_version", "timestamp", "records"}
    
    if not isinstance(snapshot, dict):
        return False
    if not required_keys.issubset(snapshot.keys()):
        return False
    if not isinstance(snapshot["records"], list):
        return False

    for record in snapshot["records"]:
        if not all(k in record for k in ("url", "content_hash", "fetched_at")):
            return False
    return True

MAKT_RECORD_TYPES = {"crawl", "lora_adapter", "dataset", "model"}

MAKT_REQUIRED = {"url", "content_hash", "fetched_at", "record_type"}

MAKT_LORA_REQUIRED = {"domain", "base_model", "size_bytes"}

def validate_makt_record(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    if not MAKT_REQUIRED.issubset(record.keys()):
        return False
    if record.get("record_type") not in MAKT_RECORD_TYPES:
        return False
    if record["record_type"] == "lora_adapter":
        if not MAKT_LORA_REQUIRED.issubset(record.keys()):
            return False
    return True


def validate_diff(diff: dict) -> bool:
    """Checks if a diff dictionary contains the required classification lists."""
    required_keys = {"new", "changed", "unchanged"}
    if not isinstance(diff, dict):
        return False
    return all(k in diff and isinstance(diff[k], list) for k in required_keys)
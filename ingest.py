import json
import os
import shutil
from pathlib import Path
from logger import logger


def ingest_outbox(indexer, outbox_dir):
    """
    Scan outbox_dir for .json result records.
    Validate, convert to snapshot record shape, merge into indexer.
    Move accepted files to processed/, rejected to rejected/.
    Returns dict with counts.
    """
    outbox = Path(outbox_dir)
    if not outbox.exists():
        logger.info(f"Ingest: outbox directory does not exist: {outbox}")
        return {"accepted": 0, "rejected": 0, "skipped": 0}

    processed_dir = outbox / "processed"
    rejected_dir = outbox / "rejected"
    processed_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    counts = {"accepted": 0, "rejected": 0, "skipped": 0}

    for record_file in sorted(outbox.glob("*.json")):
        try:
            raw = json.loads(record_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Ingest: could not parse {record_file.name}: {e}")
            shutil.move(str(record_file), str(rejected_dir / record_file.name))
            counts["rejected"] += 1
            continue

        if not _valid_pypi_record(raw):
            logger.warning(f"Ingest: invalid record schema in {record_file.name}")
            shutil.move(str(record_file), str(rejected_dir / record_file.name))
            counts["rejected"] += 1
            continue

        snapshot_record = _to_snapshot_record(raw)
        result = indexer.add_record(snapshot_record["url"], snapshot_record)
        shutil.move(str(record_file), str(processed_dir / record_file.name))

        if result == "duplicate":
            counts["skipped"] += 1
        else:
            counts["accepted"] += 1

    logger.info(
        f"Ingest complete: "
        f"{counts['accepted']} accepted, "
        f"{counts['rejected']} rejected, "
        f"{counts['skipped']} skipped"
    )
    return counts

def _valid_pypi_record(record):
    required = {"kind", "package", "version", "environment", "result", "observed_at"}
    if not isinstance(record, dict):
        return False
    if not required.issubset(record.keys()):
        return False
    if record.get("kind") != "pypi_test_result":
        return False
    if not record.get("result_hash"):
        return False
    return True


def _to_snapshot_record(raw):
    url = f"pypi://{raw['package']}/{raw['version']}/{raw['environment']}"
    return {
        "url": url,
        "content_hash": raw["result_hash"],
        "fetched_at": raw["observed_at"],
        "data": raw,
    }
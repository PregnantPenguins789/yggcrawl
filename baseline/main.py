import os
from config import SEED_URLS, SNAPSHOTS_DIR
from logger import logger
from crawler import Crawler
from indexer import Indexer
from sandbox import Sandbox

def main():
    logger.info("=== YggCrawl Phase 1: Snapshot Generation ===")

    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

    crawler = Crawler()
    indexer = Indexer()

    for url in SEED_URLS:
        content, error = Sandbox.run_isolated(crawler.fetch, url)
        if error:
            logger.warning(f"Skipping {url}: {error}")
            continue

        indexer.add_record(url, content)

    snapshot_hash = indexer.save_snapshot()
    logger.info(f"Snapshot hash: {snapshot_hash}")

    indexer.archive_snapshot()

    logger.info("=== Phase 1 Complete ===")

if __name__ == "__main__":
    main()

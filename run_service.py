#!/usr/bin/env python3
"""YggCrawl Mesh Service Entry Point

Runs YggCrawl as a long-lived service:
1. HTTP server on IPv6 (Yggdrasil-accessible) serving snapshots
2. Continuous crawl loop with peer sync
3. Graceful shutdown on SIGTERM
"""

import sys
import threading
import signal
import os

from logger import logger
import config
from network import run_server
from main import run_loop
from crawler import Crawler
from indexer import Indexer


def signal_handler(signum, frame):
    """Handle graceful shutdown on SIGTERM."""
    logger.info("Received shutdown signal, exiting...")
    sys.exit(0)


def run_service():
    """Run YggCrawl as a mesh service with HTTP server and crawl loop."""

    logger.info("=" * 70)
    logger.info("YggCrawl Mesh Service Starting")
    logger.info("=" * 70)
    logger.info(f"Node ID: {config.NODE_ID}")
    logger.info(f"HTTP Server: [{config.HTTP_HOST}]:{config.HTTP_PORT}")
    logger.info(f"Snapshots: {config.SNAPSHOTS_DIR}")
    logger.info("")

    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Create indices and crawlers
    crawler = Crawler()
    indexer = Indexer()

    # Start HTTP server in a background thread
    http_port = getattr(config, "HTTP_PORT", 8080)
    http_host = getattr(config, "HTTP_HOST", "::")

    logger.info(f"Starting HTTP server on [{http_host}]:{http_port}")
    server_thread = threading.Thread(
        target=run_server,
        args=(http_host, http_port),
        daemon=True
    )
    server_thread.start()
    logger.info("HTTP server thread started")

    # Main crawl loop (runs in foreground, blocks until interrupted)
    logger.info("Starting main crawl loop...")
    try:
        run_loop(
            indexer,
            crawler,
            getattr(config, "PEER_URLS", []),
            max_runs=None,  # Infinite loop
            sleep_seconds=5,
            sync_every=5,
            snapshot_every=5,
        )
    except KeyboardInterrupt:
        logger.info("Service interrupted, shutting down...")
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_service()

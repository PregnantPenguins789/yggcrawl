import time
from urllib.parse import urlparse, urljoin
from collections import deque
import re

import requests

from logger import logger
import config
from config import REQUEST_DELAY, REQUEST_TIMEOUT, SEED_URLS


class Crawler:
    def __init__(self):
        self.last_request_time = {}
        self.failures = {}          # Track consecutive failures per domain
        self.next_allowed = {}      # Track when we can try a domain again
        self.queue = deque(SEED_URLS)
        self.seen = set(SEED_URLS)

    def next_url(self):
        if not self.queue:
            return None
        return self.queue.popleft()

    def enqueue_links(self, links):
        for url in links:
            if url not in self.seen:
                self.seen.add(url)
                self.queue.append(url)

    def extract_links(self, html: str, base_url: str) -> list[str]:
        hrefs = re.findall(r'href=["\'](.*?)["\']', html)
        base_domain = urlparse(base_url).netloc
        links = set()

        for href in hrefs:
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)

            if parsed.scheme not in ("http", "https"):
                continue

            if parsed.netloc != base_domain:
                continue

            clean = absolute.split("#")[0]
            links.add(clean)

        return sorted(links)

    def fetch(self, url: str) -> str:
        domain = urlparse(url).netloc
        now = time.time()

        # 1. Backoff Check: Skip if domain is cooling down
        if domain in self.next_allowed and now < self.next_allowed[domain]:
            raise RuntimeError(f"Backoff active for {domain}")

        # 2. Politeness Delay: Ensure we don't hammer the host
        last = self.last_request_time.get(domain, 0)
        wait = REQUEST_DELAY - (now - last)
        if wait > 0:
            time.sleep(wait)

        logger.info(f"Fetching {url}")

        headers = {
            "User-Agent": "YggCrawl/0.1 (+https://example.com/bot)"
        }

        try:
            # 3. Execution
            resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
            resp.raise_for_status()

            # 4a. Redirect domain check: reject cross-domain redirects
            final_domain = urlparse(getattr(resp, "url", url)).netloc
            if final_domain != domain:
                raise RuntimeError(
                    f"Redirect crossed domain boundary: {domain!r} → {final_domain!r}"
                )

            # 4b. Size cap: reject oversized responses before storing
            content = resp.text
            if len(content.encode("utf-8")) > config.MAX_RESPONSE_BYTES:
                raise RuntimeError(
                    f"Response too large from {url}: >{config.MAX_RESPONSE_BYTES} bytes"
                )

            # 4. Success -> Reset failure state
            self.failures.pop(domain, None)
            self.next_allowed.pop(domain, None)

        except Exception as e:
            # 5. Failure -> Calculate and set backoff
            failures = self.failures.get(domain, 0) + 1
            self.failures[domain] = failures

            # Exponential backoff capped at 60s
            delay = min(2 ** failures, 60)
            self.next_allowed[domain] = time.time() + delay

            logger.warning(f"Fetch failed for {domain}, backoff {delay}s: {e}")
            raise

        self.last_request_time[domain] = time.time()
        logger.info(f"Fetched {url}: {len(content)} bytes")
        return content
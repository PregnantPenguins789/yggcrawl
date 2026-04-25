import time
from urllib.parse import urlparse
from logger import logger
from config import REQUEST_DELAY

class Crawler:
    def __init__(self):
        self.last_request_time = {}

    def fetch(self, url: str) -> str:
        domain = urlparse(url).netloc

        now = time.time()
        last = self.last_request_time.get(domain, 0)
        wait = REQUEST_DELAY - (now - last)
        if wait > 0:
            time.sleep(wait)

        logger.info(f"Fetching {url}")

        content = "<html><body>Sample Content</body></html>"

        self.last_request_time[domain] = time.time()
        logger.info(f"Fetched {url}: {len(content)} bytes")
        return content

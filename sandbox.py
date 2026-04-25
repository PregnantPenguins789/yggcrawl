import time
from logger import logger


class Sandbox:
    @staticmethod
    def run_isolated(func, *args, timeout=30, retries=2, backoff=0.5):
        for attempt in range(retries + 1):
            try:
                return func(*args), None
            except Exception as e:
                if attempt == retries:
                    logger.error(f"Sandbox failed after retries: {e}")
                    return None, str(e)

                logger.warning(
                    f"Sandbox attempt {attempt + 1} failed: {e}; retrying"
                )
                time.sleep(backoff * (2 ** attempt))
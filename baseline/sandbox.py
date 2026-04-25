from logger import logger

class Sandbox:
    @staticmethod
    def run_isolated(func, *args, timeout=30):
        try:
            return func(*args), None
        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return None, str(e)

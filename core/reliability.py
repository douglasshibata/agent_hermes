import logging
from typing import Dict, Any, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("agent_hermes.core.reliability")

class DeadLetterQueue:
    """
    Saves failed message deliveries or classifications into a Dead Letter Queue (DLQ)
    to prevent message loss.
    """
    def __init__(self):
        self._queue: List[Dict[str, Any]] = []

    def push(self, message: Dict[str, Any], reason: str):
        record = {
            "message": message,
            "reason": reason,
            "timestamp": getattr(message, "timestamp", None) or "N/A"
        }
        self._queue.append(record)
        logger.warning(f"[DLQ] Pushed message due to: {reason}. Payload: {message}")

    def get_all(self) -> List[Dict[str, Any]]:
        return self._queue

    def clear(self):
        self._queue.clear()


# Global in-memory instance
dlq_instance = DeadLetterQueue()


class ExponentialRetryPolicy:
    """
    Exponential backoff policy implementation using Tenacity.
    Ensures transient destination network or API failures are gracefully retried.
    """
    @staticmethod
    def get_retry_decorator(max_attempts: int = 3, min_wait: float = 1.0, max_wait: float = 8.0):
        """
        Returns a retry decorator utilizing exponential backoff.
        """
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception)),
            reraise=True
        )

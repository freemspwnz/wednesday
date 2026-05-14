from builtins import BaseException
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from tenacity import RetryCallState
from tenacity.wait import wait_base

DEFAULT_RETRY_AFTER_SECONDS: float = 5.0
NO_RETRY_AFTER_SECONDS: float = 9001.0
MAX_DELAY_SECONDS: float = 9000.0


class wait_priority(wait_base):
    def __init__(
        self,
        primary: wait_base,
        fallback: wait_base,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def __call__(self, retry_state: RetryCallState) -> float:
        wait_time = self._primary(retry_state=retry_state)
        if wait_time > MAX_DELAY_SECONDS:
            return self._fallback(retry_state=retry_state)
        return wait_time


def get_retry_after(exception: BaseException) -> float:
    retry_after = getattr(exception, "retry_after", None)
    if retry_after is not None:
        try:
            return float(retry_after)
        except (ValueError, TypeError):
            return DEFAULT_RETRY_AFTER_SECONDS
    response = getattr(exception, "response", None)
    if response is not None:
        retry_after = response.headers.get("Retry-After", None)
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
            try:
                target_date = parsedate_to_datetime(retry_after)
                now = datetime.now(UTC)
                return max(0.0, (target_date - now).total_seconds())
            except Exception:
                return DEFAULT_RETRY_AFTER_SECONDS
    return NO_RETRY_AFTER_SECONDS

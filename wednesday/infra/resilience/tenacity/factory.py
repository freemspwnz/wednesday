from builtins import BaseException
from collections.abc import Callable

from tenacity import (
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exception,
    wait_exponential_jitter,
)
from tenacity.asyncio import AsyncRetrying
from tenacity.wait import wait_base

from infra.config import RetryConfig

from .backoff import get_retry_after, wait_priority


def retrier_factory(
    *,
    config: RetryConfig,
    predicate: Callable[[BaseException], bool],
    before: Callable[[RetryCallState], None],
    after: Callable[[RetryCallState], None],
    before_sleep: Callable[[RetryCallState], None],
) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(config.attempts),
        wait=_backoff(config=config),
        retry=retry_if_exception(predicate),
        before=before,
        after=after,
        before_sleep=before_sleep,
        reraise=config.reraise,
    )


def _backoff(*, config: RetryConfig) -> wait_base:
    return wait_priority(
        wait_exception(get_retry_after),
        wait_exponential_jitter(
            initial=config.initial,
            max=config.max,
            exp_base=config.exp_base,
            jitter=config.jitter,
        ),
    )

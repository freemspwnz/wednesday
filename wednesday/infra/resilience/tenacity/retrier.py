from builtins import BaseException
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar

from tenacity import (
    RetryCallState,
    RetryError as TenacityRetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exception,
    wait_exponential_jitter,
)
from tenacity.asyncio import AsyncRetrying

from app.exceptions import AppError, MaxAttemptsExhaustedError, UnexpectedRetryError
from app.protocols import Logger, Retrier, RetryMetrics
from infra.config import RetryConfig

from .backoff import get_retry_after, wait_priority

T = TypeVar("T")
STATUS_RETRY = "retry"
STATUS_FAILED = "failed"
STATUS_SUCCESS = "success"


class Tenacity(Retrier):
    """
    Universal retry policy with adjustable exponential backoff.
    """

    def __init__(
        self,
        *,
        config: RetryConfig,
        predicate: Callable[[BaseException], bool],
        metrics: RetryMetrics,
        logger: Logger,
    ) -> None:
        self._name = config.name
        self._attempts = config.attempts
        self._reraise = config.reraise
        self._predicate = predicate
        self._backoff = wait_priority(
            wait_exception(get_retry_after),
            wait_exponential_jitter(
                initial=config.initial,
                max=config.max,
                exp_base=config.exp_base,
                jitter=config.jitter,
            ),
        )
        self._metrics = metrics
        self._logger = logger.bind(module=self.__class__.__name__, service=config.name)

    def __call__(
        self,
        func: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            return await self.execute(func, *args, **kwargs)

        return wrapper

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        try:
            retrier = AsyncRetrying(
                stop=stop_after_attempt(self._attempts),
                wait=self._backoff,
                retry=retry_if_exception(self._predicate),
                before=self._before,
                after=self._after,
                before_sleep=self._before_sleep,
                reraise=self._reraise,
            )
        except Exception as e:
            self._logger.exception(
                "Error while creating retrier",
                name=self._name,
            )
            raise UnexpectedRetryError(f"Unexpected error while creating retrier {self._name}.") from e

        try:
            async for attempt in retrier:
                with attempt:
                    result = await func(*args, **kwargs)

            attempt_number = retrier.statistics.get('attempt_number', 1)

            self._metrics.on_retry(
                name=self._name,
                attempt=attempt_number,
                status=STATUS_SUCCESS,
            )

            self._metrics.after_retry(
                name=self._name,
            )

            self._logger.debug(
                "Successful retry execution.",
                name=self._name,
                attempt=attempt_number,
            )

            return result

        except TenacityRetryError as e:
            attempt_number = retrier.statistics.get('attempt_number', 1)
            self._on_failure(retrier, e)
            raise MaxAttemptsExhaustedError(
                attempts=attempt_number,
                message=f"Failed to execute {self._name} with {attempt_number} attempt(s).",
            ) from e

        except Exception as e:
            self._on_failure(retrier, e)
            raise

    def _before_sleep(self, retry_state: RetryCallState) -> None:
        attempt_number = retry_state.attempt_number
        self._metrics.on_retry(
            name=self._name,
            attempt=attempt_number,
            status=STATUS_RETRY,
        )
        self._metrics.observe_wait_duration(
            name=self._name,
            duration=retry_state.upcoming_sleep,
        )
        self._logger.warning(
            "Retry attempt scheduled",
            name=self._name,
            attempt=attempt_number,
            sleep_duration=retry_state.upcoming_sleep,
        )

    def _after(self, retry_state: RetryCallState) -> None:
        self._metrics.after_retry(
            name=self._name,
        )

    def _before(self, retry_state: RetryCallState) -> None:
        self._metrics.before_retry()

    def _on_failure(self, retrier: AsyncRetrying, e: BaseException) -> None:
        attempt_number = retrier.statistics.get('attempt_number', 1)

        self._metrics.on_retry(name=self._name, attempt=attempt_number, status=STATUS_FAILED)

        msg = "Unexpected error while retrying"
        exc_info = True
        if isinstance(e, TenacityRetryError | AppError):
            msg = "Retry execution failed"
            exc_info = False

        self._logger.error(
            msg,
            name=self._name,
            attempt=attempt_number,
            exc_info=exc_info,
        )

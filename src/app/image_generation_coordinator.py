"""Application service для координации генерации изображений.

Координирует работу:
- CircuitBreaker (проверка и обновление состояния)
- ICache (кэширование изображений)
- ImageGenerationService (доменная генерация)
- IMetrics (метрики генерации)
"""

from __future__ import annotations

from time import perf_counter

from domain.image_generation import ImageGenerationService
from shared.base.base_service import BaseService
from shared.base.exceptions import (
    CacheError,
    CircuitBreakerOpen,
    ImageGenerationError,
    ServiceError,
    UnexpectedImageError,
)
from shared.protocols import ICache, ICircuitBreaker, ILogger, IMetrics

CACHE_VALUE_TUPLE_LENGTH = 2


class ImageGenerationCoordinator(BaseService):
    """Координатор генерации изображений.

    Отвечает за:
    - Проверку circuit breaker перед генерацией
    - Работу с кэшем изображений (проверка и запись)
    - Вызов доменного сервиса генерации
    - Запись метрик генерации (success/failed, cache hit, circuit breaker)
    """

    def __init__(
        self,
        generation_service: ImageGenerationService,
        circuit_breaker: ICircuitBreaker | None = None,
        image_cache: ICache[tuple[bytes, str]] | None = None,
        metrics: IMetrics | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует координатор генерации.

        Args:
            generation_service: Доменный сервис генерации изображений (обязателен).
            circuit_breaker: Сервис circuit breaker (опционально).
            image_cache: Сервис кэширования изображений (опционально).
            metrics: Сервис записи метрик (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._generation_service = generation_service
        self._circuit_breaker = circuit_breaker
        self._cache = image_cache
        self._metrics = metrics

    async def generate_image(
        self,
        prompt: str,
        user_id: int | None = None,
    ) -> bytes:
        """Генерирует изображение с проверкой circuit breaker и кэша.

        Выполняет следующую последовательность:
        1. Проверяет circuit breaker (если доступен)
        2. Проверяет кэш изображений (если доступен)
        3. Генерирует изображение через ImageGenerationService
        4. Обновляет circuit breaker при ошибках
        5. Записывает метрики

        Args:
            prompt: Текстовый промпт для генерации.
            user_id: Идентификатор пользователя для логирования (опционально).

        Returns:
            Байты изображения.

        Raises:
            CircuitBreakerOpen: Если circuit breaker открыт и генерация заблокирована.
            ImageGenerationError: При ошибках генерации изображения.
            UnexpectedImageError: При неожиданных ошибках.

        Note:
            При ошибках кэша генерация продолжается (graceful degradation).
        """
        start_time = perf_counter()
        user_id_str = str(user_id) if user_id is not None else None

        # 1. Проверяем circuit breaker
        await self._check_circuit_breaker(user_id_str)

        # 2. Проверяем кэш
        cached_image = await self._try_cache(prompt, user_id_str, start_time)
        if cached_image is not None:
            return cached_image

        # 3. Генерируем изображение
        self.logger.info(
            f"Начинаю генерацию изображения для промпта: {prompt[:100]}...",
            event="image_generation_started",
            user_id=user_id_str,
            status="started",
        )

        try:
            image_data = await self._generation_service.generate(prompt, user_id=user_id)
            self.logger.info(
                "Изображение успешно сгенерировано",
                event="image_generation_success",
                user_id=user_id_str,
                status="success",
            )
        except ImageGenerationError as e:
            # Обновляем circuit breaker при ошибке генерации
            await self._handle_generation_error(e, user_id_str, start_time)
            raise
        except BaseException as e:
            # Системные ошибки обрабатываются внутри handle_unexpected_error
            elapsed = perf_counter() - start_time
            unexpected_error = self.handle_unexpected_error(
                e,
                UnexpectedImageError,
                message=f"Unexpected error while generating image: {e}",
                context={
                    "event": "unexpected_generation_error",
                    "user_id": user_id_str,
                    "latency_ms": round(elapsed * 1000),
                },
            )
            await self._record_metrics("generation_failed", user_id_str)
            raise unexpected_error from e

        if not image_data:
            elapsed = perf_counter() - start_time
            self.logger.error(
                "Генерация изображения вернула пустой результат",
                event="generation_failed",
                user_id=user_id_str,
                latency_ms=round(elapsed * 1000),
                status="error",
            )
            await self._record_metrics("generation_failed", user_id_str)
            raise ImageGenerationError("Генерация изображения вернула пустой результат")

        # 4. Записываем метрики успеха
        elapsed = perf_counter() - start_time
        await self._record_metrics("generation_success", user_id_str)

        self.logger.info(
            "Генерация изображения завершена успешно",
            event="generation_completed",
            user_id=user_id_str,
            latency_ms=round(elapsed * 1000),
            status="success",
        )

        return image_data

    async def _check_circuit_breaker(self, user_id_str: str | None) -> None:
        """Проверяет circuit breaker и записывает метрики при открытии.

        Args:
            user_id_str: Идентификатор пользователя для логирования.

        Raises:
            CircuitBreakerOpen: Если circuit breaker открыт.
        """
        if self._circuit_breaker is None:
            return

        try:
            if await self._circuit_breaker.is_open():
                self.logger.warning(
                    "Circuit breaker открыт, генерация заблокирована",
                    event="generation_blocked_circuit_breaker",
                    user_id=user_id_str,
                    status="circuit_breaker_open",
                )
                await self._record_metrics("circuit_breaker_trip", user_id_str)
                raise CircuitBreakerOpen("Circuit breaker открыт, генерация изображения заблокирована")
        except CircuitBreakerOpen:
            # Пробрасываем CircuitBreakerOpen выше для явной обработки
            raise
        except ServiceError as e:
            self.logger.warning(
                f"Ошибка при проверке circuit breaker: {e}",
                event="circuit_breaker_check_error",
                status="warning",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            # При ошибке проверки circuit breaker продолжаем генерацию
            # (fail-open стратегия для проверки circuit breaker)

    async def _try_cache(
        self,
        prompt: str,
        user_id_str: str | None,
        start_time: float,
    ) -> bytes | None:
        """Пытается получить изображение из кэша.

        Args:
            prompt: Промпт для поиска в кэше.
            user_id_str: Идентификатор пользователя для логирования.
            start_time: Время начала операции для вычисления latency.

        Returns:
            Байты изображения из кэша или None, если не найдено.
        """
        if self._cache is None:
            return None

        try:
            cached_obj = await self._cache.get(prompt)
            if cached_obj:
                # Ожидаем, что реализация ICache для изображений
                # вернёт кортеж (image_data, caption) или совместимую структуру.
                if isinstance(cached_obj, tuple) and len(cached_obj) == CACHE_VALUE_TUPLE_LENGTH:
                    image_data, _cached_caption = cached_obj
                    if image_data is not None:
                        elapsed = perf_counter() - start_time
                        self.logger.info(
                            "Изображение получено из кэша",
                            event="image_cache_hit",
                            user_id=user_id_str,
                            status="cached",
                            latency_ms=round(elapsed * 1000),
                        )
                        await self._record_metrics("cache_hit", user_id_str)
                        await self._record_metrics("generation_success", user_id_str)
                        return image_data
                else:
                    self.logger.warning(
                        f"Неподдерживаемый формат значения в кэше для prompt={prompt}: {cached_obj!r}",
                    )
        except CacheError as e:
            self.logger.warning(
                f"Ошибка при проверке кэша: {e}",
                event="cache_error",
                status="warning",
                error_type=type(e).__name__,
                error_message=str(e),
            )

        return None

    async def _handle_generation_error(
        self,
        error: ImageGenerationError,
        user_id_str: str | None,
        start_time: float,
    ) -> None:
        """Обрабатывает ошибку генерации: обновляет circuit breaker и метрики.

        Args:
            error: Ошибка генерации.
            user_id_str: Идентификатор пользователя для логирования.
            start_time: Время начала операции для вычисления latency.
        """
        self.logger.error(
            f"Ошибка при генерации: {error}",
            event="generation_failed",
            user_id=user_id_str,
            status="error",
            error=str(error),
        )

        # Обновляем circuit breaker при ошибке
        if self._circuit_breaker is not None:
            try:
                await self._circuit_breaker.record_failure()
            except CircuitBreakerOpen:
                # Circuit breaker открыт после этой ошибки
                self.logger.warning(
                    "Circuit breaker открыт после ошибки генерации",
                    event="circuit_breaker_opened",
                    user_id=user_id_str,
                    status="circuit_breaker_open",
                )
                await self._record_metrics("circuit_breaker_trip", user_id_str)
                # Пробрасываем CircuitBreakerOpen для явной обработки координатором
                raise CircuitBreakerOpen("Circuit breaker открыт после ошибки генерации изображения") from error
            except ServiceError as cb_err:
                self.logger.warning(
                    f"Ошибка при записи failure в circuit breaker: {cb_err}",
                    event="circuit_breaker_error",
                    status="warning",
                    error_type=type(cb_err).__name__,
                    error_message=str(cb_err),
                )

        # Записываем метрики ошибки
        await self._record_metrics("generation_failed", user_id_str)

    async def _record_metrics(
        self,
        operation: str,
        user_id_str: str | None,
    ) -> None:
        """Записывает метрики для операции генерации.

        Args:
            operation: Тип операции ('generation_success', 'generation_failed', 'cache_hit', 'circuit_breaker_trip').
            user_id_str: Идентификатор пользователя для логирования.
        """
        if self._metrics is None:
            return

        try:
            if operation == "generation_success":
                # Используем helper-метод для получения connection из pool (вне UoW контекста)
                if hasattr(self._metrics, 'increment_generation_success_with_pool'):
                    await self._metrics.increment_generation_success_with_pool()
                else:
                    # Fallback для совместимости
                    import asyncpg

                    if hasattr(self._metrics, '_pool'):
                        metrics_pool: asyncpg.Pool = self._metrics._pool  # type: ignore[attr-defined]
                        async with metrics_pool.acquire() as conn:
                            await self._metrics.increment_generation_success(connection=conn)
            elif operation == "generation_failed":
                # Используем helper-метод для получения connection из pool (вне UoW контекста)
                if hasattr(self._metrics, 'increment_generation_failed_with_pool'):
                    await self._metrics.increment_generation_failed_with_pool()
                else:
                    # Fallback для совместимости
                    import asyncpg

                    if hasattr(self._metrics, '_pool'):
                        metrics_pool: asyncpg.Pool = self._metrics._pool  # type: ignore[attr-defined]
                        async with metrics_pool.acquire() as conn:
                            await self._metrics.increment_generation_failed(connection=conn)
            elif operation == "cache_hit":
                await self._metrics.increment_cache_hit()
            elif operation == "circuit_breaker_trip":
                await self._metrics.record_circuit_breaker_trip()
        except ServiceError as e:
            self.logger.warning(
                f"Ошибка при записи метрики {operation}: {e}",
                event="metrics_error",
                status="warning",
                error_type=type(e).__name__,
                error_message=str(e),
                user_id=user_id_str,
            )

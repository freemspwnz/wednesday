"""Application service для координации генерации изображений.

Координирует работу всех доменных и инфраструктурных сервисов для генерации,
кэширования, сохранения изображений и записи метрик.
"""

from __future__ import annotations

import time

from app.prompt_service import PromptService
from domain.caption_service import CaptionService
from domain.image_generation import ImageGenerationService
from shared.base.base_service import BaseService
from shared.base.exceptions import (
    CacheError,
    CircuitBreakerOpen,
    ImageGenerationError,
    ServiceError,
    StorageError,
    UnexpectedImageError,
)
from shared.protocols import ICache, ICircuitBreaker, IImageStorage, IImageStorageUnitOfWork, ILogger, IMetrics

CACHE_VALUE_TUPLE_LENGTH = 2


class ImageService(BaseService):
    """Application service для координации генерации изображений.

    Координирует работу:
    - ImageGenerationService (генерация изображений)
    - CaptionService (выбор подписей)
    - ImageStorageUnitOfWork (сохранение в кэш и хранилище через Unit of Work)
    - PromptService (промпты)
    - CircuitBreakerService (circuit breaker)
    - MetricsRecorder (метрики)

    Retry логика для генерации изображений находится на уровне клиента (ITextToImageClient).
    Сохранение изображений управляется через ImageStorageUnitOfWork для обеспечения согласованности данных.
    """

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        image_generation_service: ImageGenerationService,
        prompt_service: PromptService,
        storage_unit_of_work: IImageStorageUnitOfWork,
        caption_service: CaptionService | None = None,
        image_cache: ICache[tuple[bytes, str]] | None = None,
        image_storage: IImageStorage | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
        metrics: IMetrics | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис координации изображений.

        Args:
            image_generation_service: Сервис генерации изображений (обязателен).
            prompt_service: Сервис генерации промптов (обязателен).
            storage_unit_of_work: Unit of Work для сохранения изображений (обязательно).
            caption_service: Сервис работы с подписями (опционально).
            image_cache: Сервис кэширования изображений (опционально, для обратной совместимости).
            image_storage: Сервис хранения изображений (опционально, для обратной совместимости).
            circuit_breaker: Сервис circuit breaker (опционально).
            metrics: Сервис записи метрик (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._generation_service = image_generation_service
        self._prompt_service = prompt_service
        self._caption_service = caption_service
        self._circuit_breaker = circuit_breaker
        self._metrics = metrics
        self._storage_uow = storage_unit_of_work

        # Сохраняем для обратной совместимости (get_random_saved_image)
        self._cache = image_cache
        self._storage = image_storage

    async def get_random_saved_image(self) -> tuple[bytes, str] | None:
        """Возвращает случайное сохранённое изображение из файлового хранилища.

        Используется как fallback, когда генерация нового изображения недоступна.
        Если хранилище недоступно или произошла ошибка при чтении — возвращает None.
        """
        if self._storage is None:
            self.logger.warning("ImageStorageService недоступен для получения сохранённого изображения")
            return None

        try:
            return await self._storage.get_random()
        except StorageError as e:
            self.logger.warning(
                f"Ошибка при получении случайного сохранённого изображения из файлового хранилища: {e}",
                event="storage_error",
                status="warning",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return None

    async def generate_frog_image(
        self,
        user_id: int | None = None,
    ) -> tuple[bytes, str] | None:
        """Генерирует изображение жабы с полной координацией всех сервисов.

        Выполняет следующую последовательность:
        1. Проверяет circuit breaker (если доступен)
        2. Выбирает подпись через CaptionService (если доступен)
        3. Генерирует промпт через PromptService
        4. Проверяет кэш изображений (если доступен)
        5. Генерирует изображение через ImageGenerationService (retry логика на уровне клиента)
        6. Сохраняет в кэш и хранилище через ImageStorageUnitOfWork (с компенсационными действиями)
        7. Записывает метрики (если доступны)

        Args:
            user_id: Идентификатор пользователя для логирования и метрик (опционально).

        Returns:
            Кортеж (изображение в байтах, случайная подпись) или None при ошибке.

        Note:
            При ошибках на любом этапе логирование выполняется, но генерация
            продолжается (graceful degradation).
        """
        start_time = time.perf_counter()
        user_id_str = str(user_id) if user_id is not None else None

        # 1. Проверяем circuit breaker
        if self._circuit_breaker is not None:
            try:
                if await self._circuit_breaker.is_open():
                    self.logger.warning(
                        "Circuit breaker открыт, генерация пропущена",
                        event="generation_skipped_circuit_breaker",
                        user_id=user_id_str,
                        status="circuit_breaker_open",
                    )
                    if self._metrics:
                        try:
                            await self._metrics.record_circuit_breaker_trip()
                        except ServiceError as e:
                            self.logger.warning(
                                f"Ошибка при записи метрики circuit breaker: {e}",
                                event="metrics_error",
                                status="warning",
                                error_type=type(e).__name__,
                                error_message=str(e),
                            )
                    return None
            except ServiceError as e:
                self.logger.warning(
                    f"Ошибка при проверке circuit breaker: {e}",
                    event="circuit_breaker_check_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        self.logger.info(
            "Начинаю генерацию изображения жабы",
            event="generation_started",
            user_id=user_id_str,
            status="started",
        )

        # Выбираем случайную подпись
        if self._caption_service:
            try:
                self.logger.debug(
                    "Начинаю выбор подписи через CaptionService",
                    event="caption_selection_started",
                    user_id=user_id_str,
                    status="started",
                )
                caption = self._caption_service.get_random_caption()
                self.logger.debug(
                    f"Выбрана подпись: {caption}",
                    event="generation_caption_selected",
                    user_id=user_id_str,
                    status="ok",
                )
            except Exception as e:
                # Неожиданная ошибка при выборе подписи — логируем как unexpected,
                # но продолжаем генерацию с пустой подписью (graceful degradation).
                unexpected_error = UnexpectedImageError(
                    f"Unexpected error while selecting caption: {e}",
                    original_error=e,
                )
                self.logger.warning(
                    f"Ошибка при выборе подписи через CaptionService: {unexpected_error}",
                    event="caption_selection_failed",
                    user_id=user_id_str,
                    status="warning",
                    error_type=type(unexpected_error).__name__,
                    error_message=str(unexpected_error),
                )
                caption = ""
        else:
            caption = ""

        # 2. Генерируем промпт
        prompt = await self._prompt_service.generate()
        if not prompt:
            self.logger.error(
                "Не удалось сгенерировать промпт",
                event="prompt_generation_failed",
                user_id=user_id_str,
                status="error",
            )
            return None

        self.logger.info(
            f"Выбран промпт: {prompt[:100]}...",
            event="prompt_selected",
            user_id=user_id_str,
            status="ok",
        )

        # 3. Проверяем кэш
        if self._cache is not None:
            try:
                cached_obj = await self._cache.get(prompt)
                if cached_obj:
                    # Ожидаем, что реализация ICache для изображений
                    # вернёт кортеж (image_data, caption) или совместимую структуру.
                    if isinstance(cached_obj, tuple) and len(cached_obj) == CACHE_VALUE_TUPLE_LENGTH:
                        image_data, cached_caption = cached_obj
                        result_caption = str(cached_caption) or caption
                    else:
                        self.logger.warning(
                            f"Неподдерживаемый формат значения в кэше для prompt={prompt}: {cached_obj!r}",
                        )
                        image_data = None

                    if image_data is not None:
                        elapsed = time.perf_counter() - start_time
                        self.logger.info(
                            "Изображение получено из кэша",
                            event="image_cache_hit",
                            user_id=user_id_str,
                            status="cached",
                            latency_ms=round(elapsed * 1000),
                        )
                        if self._metrics:
                            try:
                                await self._metrics.increment_cache_hit()
                                await self._metrics.increment_generation_success()
                            except ServiceError as e:
                                self.logger.warning(
                                    f"Ошибка при записи метрик кэша: {e}",
                                    event="metrics_error",
                                    status="warning",
                                    error_type=type(e).__name__,
                                    error_message=str(e),
                                )
                        return image_data, result_caption
            except CacheError as e:
                self.logger.warning(
                    f"Ошибка при проверке кэша: {e}",
                    event="cache_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        # 4. Генерируем изображение (retry логика на уровне клиента)
        try:
            self.logger.info(
                f"Начинаю генерацию изображения для промпта: {prompt[:100]}...",
                event="image_generation_started",
                user_id=user_id_str,
                status="started",
            )
            image_data_result = await self._generation_service.generate(prompt, user_id=user_id)
            self.logger.info(
                "Изображение успешно сгенерировано",
                event="image_generation_success",
                user_id=user_id_str,
                status="success",
            )
        except ImageGenerationError as e:
            self.logger.error(
                f"Ошибка при генерации: {e}",
                event="generation_failed",
                user_id=user_id_str,
                status="error",
                error=str(e),
            )
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
                    if self._metrics:
                        try:
                            await self._metrics.record_circuit_breaker_trip()
                        except ServiceError:
                            pass
                    return None
                except ServiceError as cb_err:
                    self.logger.warning(
                        f"Ошибка при записи failure в circuit breaker: {cb_err}",
                        event="circuit_breaker_error",
                        status="warning",
                        error_type=type(cb_err).__name__,
                        error_message=str(cb_err),
                    )

            elapsed = time.perf_counter() - start_time
            self.logger.error(
                "Генерация изображения не удалась",
                event="generation_failed",
                user_id=user_id_str,
                latency_ms=round(elapsed * 1000),
                status="error",
            )
            if self._metrics:
                try:
                    await self._metrics.increment_generation_failed()
                except ServiceError as e:
                    self.logger.warning(
                        f"Ошибка при записи метрики failed: {e}",
                        event="metrics_error",
                        status="warning",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
            return None
        except Exception as e:
            import traceback

            elapsed = time.perf_counter() - start_time
            unexpected_error = UnexpectedImageError(
                f"Unexpected error while generating image: {e}",
                original_error=e,
            )
            self.logger.error(
                f"Неожиданная ошибка при генерации изображения: {unexpected_error}",
                event="unexpected_generation_error",
                user_id=user_id_str,
                latency_ms=round(elapsed * 1000),
                status="error",
                error_type=type(unexpected_error).__name__,
                error_message=str(unexpected_error),
                traceback=traceback.format_exc(),
            )
            if self._metrics:
                try:
                    await self._metrics.increment_generation_failed()
                except ServiceError as metrics_error:
                    self.logger.warning(
                        f"Ошибка при записи метрики failed: {metrics_error}",
                        event="metrics_error",
                        status="warning",
                        error_type=type(metrics_error).__name__,
                        error_message=str(metrics_error),
                    )
            # Пробрасываем неожиданную ошибку выше, чтобы верхний уровень мог
            # принять решение (fallback, алертинг и т.п.).
            raise unexpected_error from e

        if not image_data_result:
            elapsed = time.perf_counter() - start_time
            self.logger.error(
                "Генерация изображения вернула пустой результат",
                event="generation_failed",
                user_id=user_id_str,
                latency_ms=round(elapsed * 1000),
                status="error",
            )
            if self._metrics:
                try:
                    await self._metrics.increment_generation_failed()
                except ServiceError as e:
                    self.logger.warning(
                        f"Ошибка при записи метрики failed: {e}",
                        event="metrics_error",
                        status="warning",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
            return None

        # 5. Сохраняем в кэш и хранилище через UnitOfWork
        image_data = image_data_result
        try:
            success = await self._storage_uow.save_image(
                image_data=image_data,
                caption=caption,
                cache_key=prompt,
                storage_prefix="frog",
            )
            if success:
                self.logger.info(
                    "Изображение сохранено в хранилища",
                    event="image_saved",
                    user_id=user_id_str,
                    status="saved",
                )
            else:
                self.logger.warning("Не удалось сохранить изображение ни в одно хранилище")
        except StorageError as e:
            import traceback

            self.logger.error(
                f"Критическая ошибка при сохранении изображения: {e}",
                event="storage_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
                traceback=traceback.format_exc(),
            )
            # Пытаемся откатить
            try:
                await self._storage_uow.rollback()
            except StorageError as rollback_error:
                self.logger.error(
                    f"Ошибка при откате сохранения: {rollback_error}",
                    event="storage_rollback_error",
                    status="error",
                    error_type=type(rollback_error).__name__,
                    error_message=str(rollback_error),
                    traceback=traceback.format_exc(),
                )

        # 6. Записываем метрики успеха
        elapsed = time.perf_counter() - start_time
        if self._metrics:
            try:
                await self._metrics.increment_generation_success()
            except ServiceError as e:
                self.logger.warning(
                    f"Ошибка при записи метрики success: {e}",
                    event="metrics_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        self.logger.info(
            "Генерация изображения завершена успешно",
            event="generation_completed",
            user_id=user_id_str,
            latency_ms=round(elapsed * 1000),
            status="success",
        )

        return image_data, caption

"""Application service для координации генерации изображений.

Координирует работу всех доменных и инфраструктурных сервисов для генерации,
кэширования, сохранения изображений и записи метрик.
"""

from __future__ import annotations

import time

from services.application.image_storage_unit_of_work import ImageStorageUnitOfWork
from services.application.prompt_service import PromptService
from services.base.base_service import BaseService
from services.base.exceptions import CircuitBreakerOpen, ImageGenerationError
from services.domain.caption_service import CaptionService
from services.domain.image_generation import ImageGenerationService
from services.protocols import ICache, ICircuitBreaker, IImageStorage, IMetrics

CACHE_VALUE_TUPLE_LENGTH = 2


class ImageService(BaseService):
    """Application service для координации генерации изображений.

    Координирует работу:
    - ImageGenerationService (генерация с retry логикой)
    - CaptionService (выбор подписей)
    - ImageCacheService (кэш)
    - ImageStorageService (хранение)
    - PromptService (промпты)
    - CircuitBreakerService (circuit breaker)
    - MetricsRecorder (метрики)

    Retry логика для генерации изображений находится в ImageGenerationService (domain слой).
    """

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        image_generation_service: ImageGenerationService,
        prompt_service: PromptService,
        caption_service: CaptionService | None = None,
        image_cache: ICache[tuple[bytes, str]] | None = None,
        image_storage: IImageStorage | None = None,
        circuit_breaker: ICircuitBreaker | None = None,
        metrics: IMetrics | None = None,
        storage_unit_of_work: ImageStorageUnitOfWork | None = None,
    ) -> None:
        """Инициализирует сервис координации изображений.

        Args:
            image_generation_service: Сервис генерации изображений (обязателен).
            prompt_service: Сервис генерации промптов (обязателен).
            caption_service: Сервис работы с подписями (опционально).
            image_cache: Сервис кэширования изображений (опционально, для обратной совместимости).
            image_storage: Сервис хранения изображений (опционально, для обратной совместимости).
            circuit_breaker: Сервис circuit breaker (опционально).
            metrics: Сервис записи метрик (опционально).
            storage_unit_of_work: Unit of Work для сохранения изображений (опционально).
        """
        super().__init__()
        self._generation_service = image_generation_service
        self._prompt_service = prompt_service
        self._caption_service = caption_service
        self._circuit_breaker = circuit_breaker
        self._metrics = metrics

        # Создаём UnitOfWork, если не передан
        if storage_unit_of_work is None:
            storage_unit_of_work = ImageStorageUnitOfWork(
                cache=image_cache,
                storage=image_storage,
            )
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
        except Exception as e:  # pragma: no cover - защитный слой от неожиданных ошибок файловой системы
            self.logger.warning(
                f"Ошибка при получении случайного сохранённого изображения из файлового хранилища: {e}",
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
        5. Генерирует изображение через ImageGenerationService (retry логика в domain слое)
        6. Сохраняет в кэш и хранилище (если доступны)
        7. Записывает метрики (если доступны)

        Args:
            user_id: Идентификатор пользователя для логирования и метрик (опционально).

        Returns:
            Кортеж (изображение в байтах, случайная подпись) или None при ошибке.

        Note:
            При ошибках на любом этапе логирование выполняется, но генерация
            продолжается (graceful degradation).
        """
        start_time = time.time()
        user_id_str = str(user_id) if user_id is not None else None

        # 1. Проверяем circuit breaker
        if self._circuit_breaker is not None:
            try:
                if await self._circuit_breaker.is_open():
                    self.log_event(
                        event="generation_skipped_circuit_breaker",
                        user_id=user_id_str,
                        status="circuit_breaker_open",
                        level="warning",
                        message="Circuit breaker открыт, генерация пропущена",
                    )
                    if self._metrics:
                        try:
                            await self._metrics.record_circuit_breaker_trip()
                        except Exception as e:
                            self.logger.warning(f"Ошибка при записи метрики circuit breaker: {e}")
                    return None
            except Exception as e:
                self.logger.warning(f"Ошибка при проверке circuit breaker: {e}")

        self.log_event(
            event="generation_started",
            user_id=user_id_str,
            status="started",
            level="info",
            message="Начинаю генерацию изображения жабы",
        )

        # Выбираем случайную подпись
        if self._caption_service:
            caption = self._caption_service.get_random_caption()
        else:
            caption = ""
        self.log_event(
            event="generation_caption_selected",
            user_id=user_id_str,
            status="ok",
            level="debug",
            message=f"Выбрана подпись: {caption}",
        )

        # 2. Генерируем промпт
        prompt = await self._prompt_service.generate()
        if not prompt:
            self.log_event(
                event="prompt_generation_failed",
                user_id=user_id_str,
                status="error",
                level="error",
                message="Не удалось сгенерировать промпт",
            )
            return None

        self.log_event(
            event="prompt_selected",
            user_id=user_id_str,
            status="ok",
            level="info",
            message=f"Выбран промпт: {prompt[:100]}...",
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
                        elapsed = time.time() - start_time
                        self.log_event(
                            event="image_cache_hit",
                            user_id=user_id_str,
                            status="cached",
                            latency_ms=round(elapsed * 1000),
                            level="info",
                            message="Изображение получено из кэша",
                        )
                        if self._metrics:
                            try:
                                await self._metrics.increment_cache_hit()
                                await self._metrics.increment_generation_success()
                            except Exception as e:
                                self.logger.warning(f"Ошибка при записи метрик кэша: {e}")
                        return image_data, result_caption
            except Exception as e:
                self.logger.warning(f"Ошибка при проверке кэша: {e}")

        # 4. Генерируем изображение (retry логика теперь в ImageGenerationService)
        try:
            image_data_result = await self._generation_service.generate(prompt, user_id=user_id)
        except ImageGenerationError as e:
            self.log_event(
                event="generation_failed",
                user_id=user_id_str,
                status="error",
                extra={"error": str(e)},
                level="error",
                message=f"Ошибка при генерации: {e}",
            )
            if self._circuit_breaker is not None:
                try:
                    await self._circuit_breaker.record_failure()
                except CircuitBreakerOpen:
                    # Circuit breaker открыт после этой ошибки
                    self.log_event(
                        event="circuit_breaker_opened",
                        user_id=user_id_str,
                        status="circuit_breaker_open",
                        level="warning",
                        message="Circuit breaker открыт после ошибки генерации",
                    )
                    if self._metrics:
                        try:
                            await self._metrics.record_circuit_breaker_trip()
                        except Exception:
                            pass
                    return None
                except Exception as cb_err:
                    self.logger.warning(f"Ошибка при записи failure в circuit breaker: {cb_err}")

            elapsed = time.time() - start_time
            self.log_event(
                event="generation_failed",
                user_id=user_id_str,
                latency_ms=round(elapsed * 1000),
                status="error",
                level="error",
                message="Генерация изображения не удалась",
            )
            if self._metrics:
                try:
                    await self._metrics.increment_generation_failed()
                except Exception as e:
                    self.logger.warning(f"Ошибка при записи метрики failed: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при генерации: {e}", exc_info=True)
            elapsed = time.time() - start_time
            self.log_event(
                event="generation_failed",
                user_id=user_id_str,
                latency_ms=round(elapsed * 1000),
                status="error",
                level="error",
                message="Неожиданная ошибка при генерации изображения",
            )
            if self._metrics:
                try:
                    await self._metrics.increment_generation_failed()
                except Exception as e:
                    self.logger.warning(f"Ошибка при записи метрики failed: {e}")
            return None

        if not image_data_result:
            elapsed = time.time() - start_time
            self.log_event(
                event="generation_failed",
                user_id=user_id_str,
                latency_ms=round(elapsed * 1000),
                status="error",
                level="error",
                message="Генерация изображения вернула пустой результат",
            )
            if self._metrics:
                try:
                    await self._metrics.increment_generation_failed()
                except Exception as e:
                    self.logger.warning(f"Ошибка при записи метрики failed: {e}")
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
                self.log_event(
                    event="image_saved",
                    user_id=user_id_str,
                    status="saved",
                    level="info",
                    message="Изображение сохранено в хранилища",
                )
            else:
                self.logger.warning("Не удалось сохранить изображение ни в одно хранилище")
        except Exception as e:
            self.logger.error(f"Критическая ошибка при сохранении изображения: {e}", exc_info=True)
            # Пытаемся откатить
            try:
                await self._storage_uow.rollback()
            except Exception as rollback_error:
                self.logger.error(f"Ошибка при откате сохранения: {rollback_error}", exc_info=True)

        # 6. Записываем метрики успеха
        elapsed = time.time() - start_time
        if self._metrics:
            try:
                await self._metrics.increment_generation_success()
            except Exception as e:
                self.logger.warning(f"Ошибка при записи метрики success: {e}")

        self.log_event(
            event="generation_completed",
            user_id=user_id_str,
            latency_ms=round(elapsed * 1000),
            status="success",
            level="info",
            message="Генерация изображения завершена успешно",
        )

        return image_data, caption

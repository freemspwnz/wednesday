"""Application service для координации генерации изображений.

Оркестрирует работу:
- PromptService (генерация промптов)
- CaptionService (выбор подписей)
- ImageGenerationCoordinator (генерация изображений)
- ImageStorageCoordinator (сохранение изображений)
- IImageStorage (fallback изображения)
"""

from __future__ import annotations

from app.image_generation_coordinator import ImageGenerationCoordinator
from app.image_storage_coordinator import ImageStorageCoordinator
from app.prompt_service import PromptService
from domain.caption_service import CaptionService
from shared.base.base_service import BaseService
from shared.base.exceptions import (
    CircuitBreakerOpen,
    ImageGenerationError,
    ServiceError,
    StorageError,
    UnexpectedImageError,
)
from shared.protocols.infrastructure import IImageStorage, ILogger

PROMPT_PREVIEW_LENGTH = 100


class ImageService(BaseService):
    """Application service для координации генерации изображений.

    Оркестрирует высокоуровневый процесс генерации:
    1. Получение промпта через PromptService
    2. Выбор подписи через CaptionService
    3. Генерация изображения через ImageGenerationCoordinator
    4. Сохранение изображения через ImageStorageCoordinator
    5. Возврат результата

    Fallback изображения доступны через get_random_saved_image().
    Реализует протокол IFallbackImageProvider для использования в FallbackImageDeliveryService.
    """

    def __init__(  # noqa: PLR0913
        self,
        prompt_service: PromptService,
        generation_coordinator: ImageGenerationCoordinator,
        storage_coordinator: ImageStorageCoordinator,
        image_storage: IImageStorage,
        caption_service: CaptionService | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис координации изображений.

        Args:
            prompt_service: Сервис генерации промптов (обязателен).
            generation_coordinator: Координатор генерации изображений (обязателен).
            storage_coordinator: Координатор сохранения изображений (обязателен).
            image_storage: Сервис хранения изображений для fallback (обязателен).
                Используется для получения случайных сохраненных изображений через
                get_random_saved_image() при ошибках генерации. Без этого сервиса
                fallback функциональность не работает.
            caption_service: Сервис работы с подписями (опционально).
                Если None, используется пустая подпись. Не критично для основной
                функциональности генерации изображений.
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._prompt_service = prompt_service
        self._generation_coordinator = generation_coordinator
        self._storage_coordinator = storage_coordinator
        self._storage = image_storage
        self._caption_service = caption_service

    async def get_random_saved_image(self) -> tuple[bytes, str] | None:
        """Возвращает случайное сохранённое изображение из файлового хранилища.

        Используется как fallback, когда генерация нового изображения недоступна.
        Если произошла ошибка при чтении — возвращает None.

        Returns:
            Кортеж (байты изображения, подпись) или None, если изображение недоступно.

        Note:
            image_storage является обязательной зависимостью, поэтому этот метод
            всегда будет пытаться получить изображение. None возвращается только
            при ошибках чтения или отсутствии сохраненных изображений.
        """
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
    ) -> tuple[bytes, str]:
        """Генерирует изображение жабы с полной координацией всех сервисов.

        Выполняет следующую последовательность:
        1. Выбирает подпись через CaptionService (если доступен)
        2. Генерирует промпт через PromptService
        3. Генерирует изображение через ImageGenerationCoordinator
           (включает проверку circuit breaker, кэш, генерацию, метрики)
        4. Сохраняет изображение через ImageStorageCoordinator
           (включает сохранение через UoW, обработку ошибок)

        Args:
            user_id: Идентификатор пользователя для логирования и метрик (опционально).

        Returns:
            Кортеж (изображение в байтах, подпись).

        Raises:
            CircuitBreakerOpen: Если circuit breaker открыт и генерация заблокирована.
            ImageGenerationError: При ошибках генерации изображения.
            UnexpectedImageError: При неожиданных ошибках.

        Note:
            При ошибках на любом этапе логирование выполняется, но генерация
            продолжается (graceful degradation) где возможно.
        """
        user_id_str = str(user_id) if user_id is not None else None

        self.logger.info(
            "Начинаю генерацию изображения жабы",
            event="generation_started",
            user_id=user_id_str,
            status="started",
        )

        # 1. Выбираем случайную подпись
        caption = await self._select_caption(user_id_str)

        # 2. Генерируем промпт
        prompt = await self._generate_prompt(user_id_str)

        # 3. Генерируем изображение через координатор
        image_data = await self._generation_coordinator.generate_image(
            prompt=prompt,
            user_id=user_id,
        )

        # 4. Сохраняем изображение через координатор
        await self._storage_coordinator.save_image(
            image_data=image_data,
            caption=caption,
            cache_key=prompt,
            storage_prefix="frog",
            user_id_str=user_id_str,
        )

        self.logger.info(
            "Генерация изображения завершена успешно",
            event="generation_completed",
            user_id=user_id_str,
            status="success",
        )

        return image_data, caption

    async def _select_caption(self, user_id_str: str | None) -> str:
        """Выбирает случайную подпись через CaptionService.

        Args:
            user_id_str: Идентификатор пользователя для логирования.

        Returns:
            Подпись для изображения (может быть пустой строкой при ошибке).
        """
        if self._caption_service is None:
            return ""

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
            return caption
        except BaseException as e:
            # Неожиданная ошибка при выборе подписи — логируем как unexpected,
            # но продолжаем генерацию с пустой подписью (graceful degradation).
            self.handle_unexpected_error(
                e,
                UnexpectedImageError,
                message=f"Ошибка при выборе подписи через CaptionService: {e}",
                context={
                    "event": "caption_selection_failed",
                    "user_id": user_id_str,
                },
            )
            # Возвращаем пустую подпись для graceful degradation
            return ""

    async def _generate_prompt(self, user_id_str: str | None) -> str:
        """Генерирует промпт через PromptService.

        Args:
            user_id_str: Идентификатор пользователя для логирования.

        Returns:
            Сгенерированный промпт.

        Raises:
            ImageGenerationError: Если не удалось сгенерировать промпт.
        """
        prompt = await self._prompt_service.generate()
        if not prompt:
            self.logger.error(
                "Не удалось сгенерировать промпт",
                event="prompt_generation_failed",
                user_id=user_id_str,
                status="error",
            )
            raise ImageGenerationError("Не удалось сгенерировать промпт для изображения")

        self.logger.info(
            f"Выбран промпт: {prompt[:PROMPT_PREVIEW_LENGTH]}...",
            event="prompt_selected",
            user_id=user_id_str,
            status="ok",
        )

        return prompt

    async def generate_or_fallback(
        self,
        user_id: int | None = None,
    ) -> tuple[bytes | None, str, bool]:
        """Генерирует изображение или использует fallback при ошибке.

        Пытается сгенерировать новое изображение через generate_frog_image().
        При ошибке генерации использует случайное сохраненное изображение из архива.

        Args:
            user_id: Идентификатор пользователя для логирования и метрик (опционально).

        Returns:
            Кортеж (image_data, caption, use_fallback):
            - image_data: Байты изображения или None, если не удалось получить.
            - caption: Подпись к изображению.
            - use_fallback: True если использован fallback, False если новое изображение.
        """
        user_id_str = str(user_id) if user_id is not None else None

        try:
            # Пытаемся сгенерировать новое изображение
            image_data, caption = await self.generate_frog_image(user_id=user_id)
            return image_data, caption, False  # use_fallback = False
        except (ImageGenerationError, CircuitBreakerOpen) as e:
            # Ошибки генерации изображений - используем fallback
            self.logger.warning(
                f"Ошибка при генерации изображения, используем fallback: {e}",
                event="generation_fallback",
                status="warning",
                user_id=user_id_str,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            try:
                fallback_image = await self.get_random_saved_image()
                if fallback_image:
                    return fallback_image[0], fallback_image[1], True  # use_fallback = True
                return None, "", True
            except Exception as fallback_error:
                # Ошибка при получении fallback - логируем, но не пробрасываем
                self.logger.error(
                    f"Ошибка при получении fallback изображения: {fallback_error}",
                    event="fallback_error",
                    status="error",
                    user_id=user_id_str,
                    error_type=type(fallback_error).__name__,
                    error_message=str(fallback_error),
                    exc_info=True,
                )
                return None, "", True
        except (ValueError, TypeError, AttributeError) as e:
            # Ошибки валидации данных - не используем fallback
            self.logger.error(
                f"Ошибка валидации при генерации изображения: {e}",
                event="generation_validation_error",
                status="error",
                user_id=user_id_str,
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            return None, "", True
        except ServiceError as e:
            # Ошибки сервисного слоя - не используем fallback
            self.logger.error(
                f"Ошибка сервиса при генерации изображения: {e}",
                event="generation_service_error",
                status="error",
                user_id=user_id_str,
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            return None, "", True
        # Критические ошибки (память, системные) должны пробрасываться выше

"""Application service для проверки существования изображений по промптам.

Проверяет, было ли уже сгенерировано изображение для промпта.
Не кэширует, а проверяет постоянное хранилище (PostgreSQL + FS).
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.base.exceptions import CacheError
from shared.protocols import IImageRepo, ILogger, IPromptRepo


class ImageExistenceService(BaseService):
    """Сервис для проверки существования изображений по промптам.

    Проверяет, было ли уже сгенерировано изображение для промпта.
    Координирует PromptsRepo и ImagesRepo для проверки существования.
    """

    def __init__(
        self,
        prompts_repo: IPromptRepo,
        images_repo: IImageRepo,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис проверки существования изображений.

        Args:
            prompts_repo: Репозиторий промптов для получения prompt_hash.
            images_repo: Репозиторий изображений для проверки существования.
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._prompts_repo = prompts_repo
        self._images_repo = images_repo

    async def get_image_by_prompt(self, prompt: str) -> tuple[bytes, str] | None:
        """Проверяет существование и возвращает изображение по промпту.

        Args:
            prompt: Текст промпта для поиска.

        Returns:
            Кортеж (байты изображения, image_hash) или None, если изображение не найдено.

        Raises:
            CacheError: При ошибках доступа к хранилищу.
        """
        try:
            # Получаем prompt_hash через репозиторий (нормализация выполняется внутри)
            prompt_record = await self._prompts_repo.get_or_create_prompt(prompt)
            prompt_hash = prompt_record.prompt_hash

            # Проверяем существование изображения
            image_record = await self._images_repo.get_by_prompt_hash(prompt_hash)
            if image_record is None:
                return None

            # Загружаем файл с диска
            image_bytes = await self._images_repo.load_image_bytes(image_record)

            self.logger.debug(
                f"Изображение найдено для промпта: prompt_hash={prompt_hash}, image_hash={image_record.image_hash}",
            )
            return image_bytes, image_record.image_hash
        except FileNotFoundError as e:
            self.logger.warning(
                f"Изображение найдено в БД, но файл отсутствует на диске: {e}",
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Ошибка при проверке существования изображения: {e}",
                exc_info=True,
            )
            raise CacheError(f"Ошибка при проверке существования изображения: {e}") from e

    async def save_image_by_prompt(
        self,
        prompt: str,
        image_data: bytes,
    ) -> None:
        """Сохраняет изображение по промпту.

        Args:
            prompt: Текст промпта.
            image_data: Байты изображения для сохранения.

        Raises:
            CacheError: При ошибках сохранения.
        """
        try:
            # Регистрируем промпт в PromptsRepo (нормализация выполняется внутри)
            prompt_record = await self._prompts_repo.get_or_create_prompt(prompt)
            prompt_hash = prompt_record.prompt_hash

            # Сохраняем изображение в ImagesRepo
            # get_or_create_image автоматически сохраняет файл и создаёт запись в БД
            image_record = await self._images_repo.get_or_create_image(prompt_hash, image_data)

            self.logger.info(
                f"Изображение сохранено: prompt_hash={image_record.prompt_hash}, image_hash={image_record.image_hash}",
            )
        except Exception as e:
            self.logger.error(
                f"Ошибка при сохранении изображения: {e}",
                exc_info=True,
            )
            raise CacheError(f"Ошибка при сохранении изображения: {e}") from e

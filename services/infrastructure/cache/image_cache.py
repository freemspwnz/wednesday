"""Сервис для кэширования изображений по промптам."""

from __future__ import annotations

from hashlib import sha256

from services.base.base_service import BaseService
from services.base.exceptions import CacheError
from utils.images_store import ImagesStore
from utils.prompts_store import PromptsStore


class ImageCacheService(BaseService):
    """Сервис для кэширования изображений по промптам.

    Использует ImagesStore и PromptsStore для работы с кэшем изображений
    в базе данных PostgreSQL.
    """

    def __init__(
        self,
        images_store: ImagesStore | None = None,
        prompts_store: PromptsStore | None = None,
    ) -> None:
        """Инициализирует сервис кэширования изображений.

        Args:
            images_store: Экземпляр ImagesStore для работы с изображениями.
                Если None, создаётся новый экземпляр.
            prompts_store: Экземпляр PromptsStore для работы с промптами.
                Если None, создаётся новый экземпляр.
        """
        super().__init__()
        self._images_store = images_store or ImagesStore()
        self._prompts_store = prompts_store or PromptsStore()

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        """Нормализует промпт для вычисления хеша.

        Args:
            prompt: Исходный текст промпта.

        Returns:
            Нормализованный текст промпта.
        """
        return prompt.strip()

    @staticmethod
    def _compute_prompt_hash(normalized: str) -> str:
        """Вычисляет SHA256-хеш нормализованного промпта.

        Args:
            normalized: Нормализованный текст промпта.

        Returns:
            SHA256-хеш в hex-представлении (64 символа).
        """
        return sha256(normalized.encode("utf-8")).hexdigest()

    async def get_by_prompt(self, prompt: str) -> tuple[bytes, str] | None:
        """Получает изображение из кэша по промпту.

        Нормализует промпт, вычисляет prompt_hash и ищет изображение в кэше.

        Args:
            prompt: Текст промпта для поиска.

        Returns:
            Кортеж (байты изображения, caption) или None, если изображение не найдено.

        Raises:
            CacheError: При ошибках доступа к кэшу.
        """
        try:
            # Нормализуем промпт и вычисляем hash
            normalized = self._normalize_prompt(prompt)
            prompt_hash = self._compute_prompt_hash(normalized)

            # Ищем изображение по prompt_hash
            image_record = await self._images_store.get_by_prompt_hash(prompt_hash)
            if image_record is None:
                return None

            # Загружаем байты изображения
            image_bytes = self._images_store.load_image_bytes(image_record)

            # Возвращаем байты и image_hash в качестве caption
            return image_bytes, image_record.image_hash
        except FileNotFoundError as e:
            self.logger.warning(
                f"Изображение найдено в кэше, но файл отсутствует на диске: {e}",
            )
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при получении изображения из кэша: {e}", exc_info=True)
            raise CacheError(f"Ошибка при получении изображения из кэша: {e}") from e

    async def get_by_hash(self, prompt_hash: str) -> tuple[bytes, str] | None:
        """Получает изображение из кэша по prompt_hash.

        Args:
            prompt_hash: SHA256-хеш нормализованного промпта.

        Returns:
            Кортеж (байты изображения, image_hash) или None, если изображение не найдено.

        Raises:
            CacheError: При ошибках доступа к кэшу.
        """
        try:
            # Ищем изображение по prompt_hash
            image_record = await self._images_store.get_by_prompt_hash(prompt_hash)
            if image_record is None:
                return None

            # Загружаем байты изображения
            image_bytes = self._images_store.load_image_bytes(image_record)

            # Возвращаем байты и image_hash
            return image_bytes, image_record.image_hash
        except FileNotFoundError as e:
            self.logger.warning(
                f"Изображение найдено в кэше, но файл отсутствует на диске: {e}",
            )
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при получении изображения из кэша: {e}", exc_info=True)
            raise CacheError(f"Ошибка при получении изображения из кэша: {e}") from e

    async def save(
        self,
        prompt: str,
        image_data: bytes,
        caption: str,
    ) -> None:
        """Сохраняет изображение в кэш.

        Нормализует промпт, регистрирует его в PromptsStore и сохраняет
        изображение в ImagesStore.

        Args:
            prompt: Текст промпта.
            image_data: Байты изображения для сохранения.
            caption: Подпись к изображению (не используется при сохранении, но
                сохраняется для совместимости интерфейса).

        Raises:
            CacheError: При ошибках сохранения в кэш.
        """
        try:
            # Регистрируем промпт в PromptsStore (нормализация выполняется внутри)
            prompt_record = await self._prompts_store.get_or_create_prompt(prompt)
            prompt_hash = prompt_record.prompt_hash

            # Сохраняем изображение в ImagesStore
            # get_or_create_image автоматически сохраняет файл и создаёт запись в БД
            image_record = await self._images_store.get_or_create_image(prompt_hash, image_data)

            self.logger.info(
                f"Изображение сохранено в кэш: prompt_hash={image_record.prompt_hash}, "
                f"image_hash={image_record.image_hash}",
            )
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении изображения в кэш: {e}", exc_info=True)
            raise CacheError(f"Ошибка при сохранении изображения в кэш: {e}") from e

"""Сервис для кэширования изображений по промптам."""

from __future__ import annotations

from hashlib import sha256

from services.base.base_service import BaseService
from services.base.exceptions import CacheError
from services.protocols import ICache, IImageRepo, IPromptRepo

IMAGE_CACHE_VALUE_TUPLE_LENGTH = 2


class ImageCacheService(BaseService, ICache[tuple[bytes, str]]):
    """Сервис для кэширования изображений по промптам.

    Использует ImagesRepo и PromptsRepo для работы с кэшем изображений
    в базе данных PostgreSQL.
    """

    def __init__(
        self,
        images_repo: IImageRepo,
        prompts_repo: IPromptRepo,
    ) -> None:
        """Инициализирует сервис кэширования изображений.

        Args:
            images_repo: Экземпляр репозитория изображений (IImageRepo).
            prompts_repo: Экземпляр репозитория промптов (IPromptRepo).
        """
        super().__init__()
        self._images_repo = images_repo
        self._prompts_repo = prompts_repo

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
            image_record = await self._images_repo.get_by_prompt_hash(prompt_hash)
            if image_record is None:
                return None

            # Загружаем байты изображения
            image_bytes = await self._images_repo.load_image_bytes(image_record)

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
            image_record = await self._images_repo.get_by_prompt_hash(prompt_hash)
            if image_record is None:
                return None

            # Загружаем байты изображения
            image_bytes = await self._images_repo.load_image_bytes(image_record)

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
            # Регистрируем промпт в PromptsRepo (нормализация выполняется внутри)
            prompt_record = await self._prompts_repo.get_or_create_prompt(prompt)
            prompt_hash = prompt_record.prompt_hash

            # Сохраняем изображение в ImagesRepo
            # get_or_create_image автоматически сохраняет файл и создаёт запись в БД
            image_record = await self._images_repo.get_or_create_image(prompt_hash, image_data)

            self.logger.info(
                f"Изображение сохранено в кэш: prompt_hash={image_record.prompt_hash}, "
                f"image_hash={image_record.image_hash}",
            )
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении изображения в кэш: {e}", exc_info=True)
            raise CacheError(f"Ошибка при сохранении изображения в кэш: {e}") from e

    async def get(self, key: str) -> tuple[bytes, str] | None:
        """Реализация протокола ICache.get для кэша изображений.

        Для совместимости с существующей логикой key трактуется как текст промпта.
        Возвращает кортеж (байты изображения, caption), как и get_by_prompt().
        """
        return await self.get_by_prompt(key)

    async def set(self, key: str, value: tuple[bytes, str], ttl: int | None = None) -> None:
        """Реализация протокола ICache.set для кэша изображений.

        Ожидает value в формате (image_data: bytes, caption: str | object).
        """
        try:
            if not isinstance(value, tuple) or len(value) != IMAGE_CACHE_VALUE_TUPLE_LENGTH:
                raise CacheError("Expected value as tuple[bytes, str] for ImageCacheService.set()")

            image_data_obj, caption_obj = value
            if not isinstance(image_data_obj, bytes | bytearray):
                raise CacheError("First element of value must be bytes-like for ImageCacheService.set()")

            image_bytes = bytes(image_data_obj)
            caption_str = str(caption_obj)

            await self.save(prompt=key, image_data=image_bytes, caption=caption_str)
        except CacheError:
            raise
        except Exception as e:  # pragma: no cover - защитный слой от неожиданных типов
            self.logger.error(f"Ошибка при установке значения в кэш через set(): {e}", exc_info=True)
            raise CacheError(f"Ошибка при установке значения в кэш: {e}") from e

    async def delete(self, key: str) -> None:
        """Реализация протокола ICache.delete.

        В текущей версии кэша удаление по ключу не требуется бизнес-логикой,
        поэтому метод является no-op с логированием для диагностики.
        """
        self.logger.debug(f"ICache.delete() вызван для ImageCacheService, key={key} (no-op)")

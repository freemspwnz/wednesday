"""Сервис для работы с файловым хранилищем изображений."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime
from pathlib import Path

from shared.base.base_service import BaseService
from shared.base.exceptions import StorageError
from shared.paths import FROGS_DIR

MAX_FILES_DEFAULT = 30


class ImageStorageService(BaseService):
    """Сервис для сохранения и получения изображений из файлового хранилища."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        """Инициализирует сервис хранилища изображений.

        Args:
            base_dir: Базовая директория для хранения изображений. Если None,
                используется FROGS_DIR по умолчанию.
        """
        super().__init__()
        if base_dir is None:
            self.base_dir = FROGS_DIR
        elif isinstance(base_dir, str):
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = base_dir

    async def save(
        self,
        image_data: bytes,
        folder: Path | str | None = None,
        prefix: str = "frog",
        max_files: int = MAX_FILES_DEFAULT,
    ) -> str:
        """Сохраняет изображение в файловое хранилище.

        Сохраняет изображение в указанную папку с временной меткой в имени файла.
        При достижении лимита max_files автоматически удаляет самые старые файлы.

        Args:
            image_data: Содержимое изображения в байтах.
            folder: Папка для сохранения. Если None, используется base_dir.
            prefix: Префикс имени файла (по умолчанию "frog").
            max_files: Максимальное количество файлов в папке (по умолчанию 30).

        Returns:
            Путь к сохраненному файлу.

        Raises:
            StorageError: При ошибках файловой системы (недостаточно прав, места и т.д.).
        """
        try:
            # Определяем путь для сохранения
            if folder is None:
                path = self.base_dir
            elif isinstance(folder, str):
                path = Path(folder)
            else:
                path = folder

            # Создаем директорию асинхронно
            await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)

            # Сохраняем новый файл асинхронно
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = path / f"{prefix}_{ts}.png"

            await asyncio.to_thread(file_path.write_bytes, image_data)
            self.logger.info(f"Изображение сохранено: {file_path}")

            # Ограничиваем количество файлов в папке асинхронно
            await self._cleanup_old_files(path, max_files, file_path)

            return str(file_path)
        except OSError as e:
            raise StorageError(f"Ошибка при сохранении изображения: {e}") from e
        except Exception as e:
            raise StorageError(f"Неожиданная ошибка при сохранении изображения: {e}") from e

    async def _cleanup_old_files(
        self,
        path: Path,
        max_files: int,
        current_file: Path,
    ) -> None:
        """Удаляет старые файлы при превышении лимита.

        Args:
            path: Путь к директории с файлами.
            max_files: Максимальное количество файлов.
            current_file: Только что сохраненный файл (не удаляется).
        """
        try:
            # Получаем все PNG файлы асинхронно
            all_files = await asyncio.to_thread(lambda: list(path.glob("*.png")))

            if len(all_files) > max_files:
                # Сортируем по времени модификации: новейшие файлы первыми
                def get_mtime(p: Path) -> float:
                    return p.stat().st_mtime

                files_sorted = await asyncio.to_thread(
                    lambda: sorted(all_files, key=get_mtime, reverse=True),
                )

                # Удаляем самые старые файлы (начиная с индекса max_files)
                files_to_delete = files_sorted[max_files:]
                deleted_count = 0

                for old_file in files_to_delete:
                    try:
                        # Не удаляем только что сохраненный файл
                        if old_file != current_file:
                            await asyncio.to_thread(old_file.unlink, missing_ok=True)
                            deleted_count += 1
                            self.logger.debug(f"Удален старый файл: {old_file.name}")
                    except Exception as e:
                        self.logger.warning(f"Не удалось удалить файл {old_file.name}: {e}")

                if deleted_count > 0:
                    self.logger.info(
                        f"Удалено {deleted_count} старых файлов. "
                        f"Всего файлов: {len(all_files) - deleted_count} (лимит: {max_files})",
                    )
                else:
                    self.logger.warning(
                        f"Достигнут лимит файлов ({max_files}), но не удалось удалить старые",
                    )
            else:
                self.logger.debug(f"Всего файлов в папке: {len(all_files)} (лимит: {max_files})")
        except Exception as e:
            self.logger.error(f"Ошибка при ограничении количества файлов в {path}: {e}")
            # Продолжаем работу, даже если не удалось очистить старые файлы

    async def get_random(
        self,
        folder: Path | str | None = None,
    ) -> tuple[bytes, str] | None:
        """Получает случайное изображение из файлового хранилища.

        Выбирает случайный PNG файл из указанной папки и возвращает его содержимое
        вместе с именем файла.

        Args:
            folder: Папка с сохраненными изображениями. Если None, используется base_dir.

        Returns:
            Кортеж (изображение в байтах, имя файла) или None если:
            - папка не существует.
            - в папке нет PNG файлов.
            - произошла ошибка при чтении файла.

        Raises:
            StorageError: При критических ошибках доступа к файловой системе.
        """
        try:
            # Определяем путь
            if folder is None:
                path = self.base_dir
            elif isinstance(folder, str):
                path = Path(folder)
            else:
                path = folder

            # Проверяем существование папки асинхронно
            exists = await asyncio.to_thread(path.exists)
            if not exists:
                self.logger.warning(f"Папка с сохранёнными изображениями не существует: {path}")
                return None

            # Получаем все PNG файлы асинхронно
            image_files = await asyncio.to_thread(lambda: list(path.glob("*.png")))
            if not image_files:
                self.logger.warning(f"Нет сохраненных изображений в папке {path}")
                return None

            # Выбираем случайный файл
            random_file = random.choice(image_files)

            # Читаем файл асинхронно
            image_data = await asyncio.to_thread(random_file.read_bytes)
            file_name = random_file.name

            self.logger.info(f"Загружено случайное изображение: {random_file}")
            return image_data, file_name
        except OSError as e:
            self.logger.error(f"Ошибка при получении случайного изображения из {folder}: {e}")
            raise StorageError(f"Ошибка доступа к файловой системе: {e}") from e
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при получении случайного изображения: {e}")
            return None

    async def get_random_from_archive(self) -> tuple[bytes, str] | None:
        """Возвращает случайное сохранённое изображение из базовой директории.

        Используется как fallback, когда генерация нового изображения недоступна.
        Возвращает кортеж (image_data, file_name).
        """
        return await self.get_random(folder=self.base_dir)

    async def get_by_path(self, path: str) -> bytes:
        """Загружает изображение по пути к файлу.

        Args:
            path: Путь к файлу в хранилище (может быть абсолютным или относительным).

        Returns:
            Байты изображения.

        Raises:
            FileNotFoundError: Если файл не найден.
            StorageError: При ошибках чтения файла.
        """
        try:
            file_path = Path(path)
            # Если путь относительный, используем base_dir
            if not file_path.is_absolute():
                file_path = self.base_dir / file_path

            if not await asyncio.to_thread(file_path.exists):
                raise FileNotFoundError(f"Файл не найден: {file_path}")

            image_data = await asyncio.to_thread(file_path.read_bytes)
            self.logger.debug(f"Изображение загружено из хранилища: {file_path}")
            return image_data
        except FileNotFoundError:
            raise
        except OSError as e:
            raise StorageError(f"Ошибка при чтении файла {path}: {e}") from e
        except Exception as e:
            raise StorageError(f"Неожиданная ошибка при чтении файла {path}: {e}") from e

    async def delete(self, path: str) -> None:
        """Удаляет файл из хранилища.

        Args:
            path: Путь к файлу для удаления.

        Raises:
            FileNotFoundError: Если файл не найден.
            StorageError: При ошибках файловой системы.
        """
        try:
            file_path = Path(path)
            # Проверяем существование файла асинхронно
            exists = await asyncio.to_thread(file_path.exists)
            if not exists:
                raise FileNotFoundError(f"Файл не найден: {path}")

            # Удаляем файл асинхронно
            await asyncio.to_thread(file_path.unlink)
            self.logger.info(f"Файл удален из хранилища: {path}")
        except FileNotFoundError:
            raise
        except OSError as e:
            raise StorageError(f"Ошибка при удалении файла {path}: {e}") from e
        except Exception as e:
            raise StorageError(f"Неожиданная ошибка при удалении файла {path}: {e}") from e

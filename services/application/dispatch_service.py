"""Application‑сервис для cron‑логики отправки Wednesday Frog.

Инкапсулирует работу с:
- `dispatch_registry` — чтобы не отправлять повторно в один и тот же слот;
- `usage` — счётчик использований;
- `metrics` — метрики успешных/неуспешных рассылок;
- `chats` — список целевых чатов;
- `image_service` — генерация и fallback изображений.

Отправка сообщений в Telegram и форматирование пользовательских текстов
остаются в `WednesdayBot` и передаются сюда через коллбеки.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from telegram.error import NetworkError, TelegramError

from services.application.image_service import ImageService
from services.base.base_service import BaseService
from utils.chats_repo import ChatsRepo
from utils.dispatch_registry import DispatchRegistry
from utils.metrics import Metrics
from utils.retry import retry_on_connect_error
from utils.usage_tracker import UsageTracker


class DispatchResult(dict):
    """Простейший контейнер результата отправки.

    Ключи:
        - slot_date: дата слота (YYYY-MM-DD)
        - slot_time: время слота (HH:MM)
        - total_targets: всего целевых чатов
        - success_count: количество успешных отправок
        - failed_count: количество неуспешных отправок (по Telegram/программным ошибкам)
        - used_fallback: использован ли fallback‑сценарий вместо свежей генерации
    """


class DispatchService(BaseService):
    """Application‑сервис для выполнения рассылки Wednesday Frog."""

    def __init__(
        self,
        *,
        usage: UsageTracker,
        chats: ChatsRepo,
        dispatch_registry: DispatchRegistry,
        metrics: Metrics,
        image_service: ImageService | None,
    ) -> None:
        super().__init__()
        self._usage = usage
        self._chats = chats
        self._dispatch_registry = dispatch_registry
        self._metrics = metrics
        self._image_service = image_service

    @staticmethod
    def _init_result(slot_date: str, slot_time: str) -> DispatchResult:
        """Инициализирует результат рассылки.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.

        Returns:
            Инициализированный DispatchResult.
        """
        return DispatchResult(
            slot_date=slot_date,
            slot_time=slot_time,
            total_targets=0,
            success_count=0,
            failed_count=0,
            used_fallback=False,
        )

    async def _prepare_targets(
        self,
        main_chat_id: str | None,
        send_error_message: Callable[[str], Awaitable[None]],
        result: DispatchResult,
    ) -> set[int]:
        """Подготавливает список целевых чатов для рассылки.

        Args:
            main_chat_id: Основной чат (строковый ID) для рассылки, если задан.
            send_error_message: Коллбек для отправки краткого сообщения об ошибке в основной чат.
            result: Результат рассылки для обновления total_targets.

        Returns:
            Множество ID целевых чатов. Пустое множество, если нет чатов для отправки.
        """
        targets: set[int] = set(await self._chats.list_chat_ids() or [])
        if main_chat_id:
            try:
                chat_id_int: int = int(str(main_chat_id))
                targets.add(chat_id_int)
            except (ValueError, TypeError):
                pass

        result["total_targets"] = len(targets)

        if not targets:
            self.logger.warning("Нет целевых чатов для отправки сообщения")
            await send_error_message("Нет настроенных чатов для отправки")

        return targets

    async def _already_dispatched_for_all(
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
    ) -> bool:
        """Проверяет, отправляли ли уже в этот слот во все целевые чаты.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.

        Returns:
            True, если уже отправлено во все чаты, иначе False.
        """
        for target_chat in targets:
            if not await self._dispatch_registry.is_dispatched(
                slot_date,
                slot_time,
                target_chat,
            ):
                return False
        return True

    async def _generate_image(self) -> tuple[bytes, str] | None:
        """Генерирует изображение жабы.

        Returns:
            Кортеж (image_data, caption) при успешной генерации, иначе None.
        """
        if self._image_service is None:
            self.logger.error("ImageService недоступен, пропускаю генерацию")
            return None

        return await self._image_service.generate_frog_image()

    async def _send_single_photo(  # noqa: PLR0913, PLR0917
        self,
        target_chat: int,
        slot_date: str,
        slot_time: str,
        image_data: bytes,
        caption: str,
        send_error_message: Callable[[str], Awaitable[None]],
        send_photo: Callable[..., Awaitable[None]],
        result: DispatchResult,
    ) -> None:
        """Отправляет одно фото в указанный чат.

        Args:
            target_chat: ID целевого чата.
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            image_data: Данные изображения.
            caption: Подпись к изображению.
            send_error_message: Коллбек для отправки краткого сообщения об ошибке.
            send_photo: Низкоуровневый коллбек Telegram‑бота для отправки фото.
            result: Результат рассылки для обновления счетчиков.
        """
        try:
            await retry_on_connect_error(
                send_photo,
                chat_id=target_chat,
                photo=image_data,
                caption=caption,
                max_retries=3,
                delay=2.0,
                handle_rate_limit=True,
            )
            # Отмечаем в реестре успешную отправку
            await self._dispatch_registry.mark_dispatched(
                slot_date,
                slot_time,
                target_chat,
            )
            # Инкрементируем счётчик после успешной отправки
            await self._usage.increment(1)
            try:
                await self._metrics.increment_dispatch_success()
            except Exception:  # pragma: no cover - метрики не критичны
                pass
            result["success_count"] += 1
            self.logger.info(f"Жаба отправлена в чат {target_chat}")
        except (TelegramError, NetworkError) as send_error:
            # Сетевые/Telegram-ошибки после всех попыток
            error_str = str(send_error).lower()
            is_network = isinstance(send_error, NetworkError) or any(
                kw in error_str for kw in ("connection", "timeout", "network")
            )
            log_msg = (
                f"Сетевая/Telegram-ошибка отправки в чат {target_chat}: {send_error}"
                if is_network
                else f"Ошибка Telegram API при отправке в чат {target_chat}: {send_error}"
            )
            self.logger.error(log_msg)
            try:
                await send_error_message(
                    f"Не удалось отправить изображение в чат {target_chat}",
                )
            except Exception:  # pragma: no cover - уведомление не критично
                pass
            try:
                await self._metrics.increment_dispatch_failed()
            except Exception:  # pragma: no cover
                pass
            result["failed_count"] += 1
        except Exception as send_error:
            # Неожиданные программные ошибки
            self.logger.error(
                f"Неожиданная программная ошибка при отправке изображения в чат {target_chat}: {send_error}",
                exc_info=True,
            )
            try:
                await send_error_message(
                    f"Не удалось отправить изображение в чат {target_chat} из-за внутренней ошибки",
                )
            except Exception:  # pragma: no cover
                pass
            try:
                await self._metrics.increment_dispatch_failed()
            except Exception:  # pragma: no cover
                pass
            result["failed_count"] += 1

    async def _send_to_targets(  # noqa: PLR0913, PLR0917
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
        image_data: bytes,
        caption: str,
        send_error_message: Callable[[str], Awaitable[None]],
        send_photo: Callable[..., Awaitable[None]],
        result: DispatchResult,
    ) -> DispatchResult:
        """Отправляет изображение во все целевые чаты.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.
            image_data: Данные изображения.
            caption: Подпись к изображению.
            send_error_message: Коллбек для отправки краткого сообщения об ошибке.
            send_photo: Низкоуровневый коллбек Telegram‑бота для отправки фото.
            result: Результат рассылки для обновления счетчиков.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        for target_chat in targets:
            # Проверяем, не было ли уже отправлено в этот чат в этот тайм-слот
            if await self._dispatch_registry.is_dispatched(
                slot_date,
                slot_time,
                target_chat,
            ):
                self.logger.info(
                    f"Пропускаем отправку в {target_chat} - уже отправлено в слот {slot_date}_{slot_time}",
                )
                continue

            await self._send_single_photo(
                target_chat,
                slot_date,
                slot_time,
                image_data,
                caption,
                send_error_message,
                send_photo,
                result,
            )

        return result

    async def _send_fallback_to_targets(  # noqa: PLR0913, PLR0917
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
        send_user_friendly_error: Callable[[int], Awaitable[None]],
        send_fallback_image: Callable[[int], Awaitable[bool]],
        result: DispatchResult,
    ) -> None:
        """Отправляет fallback сообщения и изображения во все целевые чаты.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.
            send_user_friendly_error: Коллбек для отправки дружелюбного сообщения об ошибке в чат.
            send_fallback_image: Коллбек для отправки fallback‑изображения в чат.
            result: Результат рассылки для обновления счетчиков.
        """
        for target_chat in targets:
            try:
                # Проверяем, не было ли уже отправлено в этот чат в этот тайм-слот
                if await self._dispatch_registry.is_dispatched(
                    slot_date,
                    slot_time,
                    target_chat,
                ):
                    self.logger.info(
                        f"Пропускаем fallback отправку в {target_chat} - уже отправлено в слот {slot_date}_{slot_time}",
                    )
                    continue

                # Отправляем дружелюбное сообщение
                await send_user_friendly_error(target_chat)

                # Отправляем случайное изображение
                if await send_fallback_image(target_chat):
                    # Отмечаем в реестре успешную отправку
                    await self._dispatch_registry.mark_dispatched(
                        slot_date,
                        slot_time,
                        target_chat,
                    )
                    try:
                        await self._metrics.increment_dispatch_success()
                    except Exception:  # pragma: no cover
                        pass
                    result["success_count"] += 1

            except Exception as send_error:
                self.logger.error(f"Ошибка при отправке fallback в чат {target_chat}: {send_error}")
                result["failed_count"] += 1

    async def _handle_generation_failure(  # noqa: PLR0913, PLR0917
        self,
        slot_date: str,
        slot_time: str,
        main_chat_id: str | None,
        send_admin_error: Callable[[str], Awaitable[None]],
        send_user_friendly_error: Callable[[int], Awaitable[None]],
        send_fallback_image: Callable[[int], Awaitable[bool]],
        result: DispatchResult,
    ) -> DispatchResult:
        """Обрабатывает ситуацию, когда генерация изображения не удалась.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            main_chat_id: Основной чат (строковый ID) для рассылки, если задан.
            send_admin_error: Коллбек для отправки детального сообщения об ошибке администраторам.
            send_user_friendly_error: Коллбек для отправки дружелюбного сообщения об ошибке в чат.
            send_fallback_image: Коллбек для отправки fallback‑изображения в чат.
            result: Результат рассылки для обновления счетчиков.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        error_details = (
            "Не удалось сгенерировать изображение жабы для среды. "
            "API вернул None (возможные причины: лимит API, circuit breaker, "
            "ошибка генерации)"
        )
        self.logger.error(error_details)

        # Отправляем детальное сообщение администратору
        await send_admin_error(error_details)

        # Отправляем дружелюбные сообщения и случайные изображения во все целевые чаты
        targets = set(await self._chats.list_chat_ids() or [])
        if main_chat_id:
            try:
                chat_id_val: int = int(str(main_chat_id))
                targets.add(chat_id_val)
            except (ValueError, TypeError):
                pass

        result["total_targets"] = len(targets)
        result["used_fallback"] = True

        await self._send_fallback_to_targets(
            slot_date,
            slot_time,
            targets,
            send_user_friendly_error,
            send_fallback_image,
            result,
        )

        return result

    async def _handle_unexpected_error(  # noqa: PLR0913, PLR0917
        self,
        e: Exception,
        slot_date: str,
        slot_time: str,
        main_chat_id: str | None,
        send_admin_error: Callable[[str], Awaitable[None]],
        send_user_friendly_error: Callable[[int], Awaitable[None]],
        send_fallback_image: Callable[[int], Awaitable[bool]],
        result: DispatchResult,
    ) -> DispatchResult:
        """Обрабатывает неожиданные ошибки при выполнении рассылки.

        Args:
            e: Исключение, которое произошло.
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            main_chat_id: Основной чат (строковый ID) для рассылки, если задан.
            send_admin_error: Коллбек для отправки детального сообщения об ошибке администраторам.
            send_user_friendly_error: Коллбек для отправки дружелюбного сообщения об ошибке в чат.
            send_fallback_image: Коллбек для отправки fallback‑изображения в чат.
            result: Результат рассылки для обновления счетчиков.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        import traceback

        error_details = f"Произошла ошибка при отправке жабы: {e!s}"
        self.logger.error(error_details, exc_info=True)

        # Отправляем детальное сообщение администратору с трейcом
        full_error = traceback.format_exc()
        # Обрезаем трейс до последних 2000 символов (важная информация обычно в конце)
        max_trace_length = 2000
        if len(full_error) > max_trace_length:
            full_error = "..." + full_error[-max_trace_length:]
        await send_admin_error(
            f"{error_details}\n\nТрейс (последние {max_trace_length} символов):\n{full_error}",
        )

        # Отправляем дружелюбные сообщения и случайные изображения во все целевые чаты
        targets = set(await self._chats.list_chat_ids() or [])
        if main_chat_id:
            try:
                chat_id_error_val: int = int(str(main_chat_id))
                targets.add(chat_id_error_val)
            except (ValueError, TypeError):
                pass

        result["total_targets"] = len(targets)
        result["used_fallback"] = True

        await self._send_fallback_to_targets(
            slot_date,
            slot_time,
            targets,
            send_user_friendly_error,
            send_fallback_image,
            result,
        )

        return result

    async def send_wednesday_frog(  # noqa: PLR0913
        self,
        *,
        slot_date: str,
        slot_time: str,
        main_chat_id: str | None,
        send_error_message: Callable[[str], Awaitable[None]],
        send_admin_error: Callable[[str], Awaitable[None]],
        send_user_friendly_error: Callable[[int], Awaitable[None]],
        send_fallback_image: Callable[[int], Awaitable[bool]],
        send_photo: Callable[..., Awaitable[None]],
    ) -> DispatchResult:
        """Выполняет рассылку жабы в указанный слот.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            main_chat_id: Основной чат (строковый ID) для рассылки, если задан.
            send_error_message: Коллбек для отправки краткого сообщения об ошибке в основной чат.
            send_admin_error: Коллбек для отправки детального сообщения об ошибке администраторам.
            send_user_friendly_error: Коллбек для отправки дружелюбного сообщения об ошибке в чат.
            send_fallback_image: Коллбек для отправки fallback‑изображения в чат.
            send_photo: Низкоуровневый коллбек Telegram‑бота для отправки фото (как в `bot.send_photo`).

        Returns:
            DispatchResult с агрегированными счетчиками по рассылке.
        """
        result = DispatchService._init_result(slot_date, slot_time)

        try:
            targets = await self._prepare_targets(main_chat_id, send_error_message, result)
            if not targets:
                return result

            if await self._already_dispatched_for_all(slot_date, slot_time, targets):
                self.logger.info(
                    f"Уже отправлено ранее для всех чатов в слот {slot_date}_{slot_time}. Пропускаю генерацию.",
                )
                return result

            generation_result = await self._generate_image()
            if generation_result is None:
                return await self._handle_generation_failure(
                    slot_date,
                    slot_time,
                    main_chat_id,
                    send_admin_error,
                    send_user_friendly_error,
                    send_fallback_image,
                    result,
                )

            image_data, caption = generation_result
            return await self._send_to_targets(
                slot_date,
                slot_time,
                targets,
                image_data,
                caption,
                send_error_message,
                send_photo,
                result,
            )
        except Exception as e:
            return await self._handle_unexpected_error(
                e,
                slot_date,
                slot_time,
                main_chat_id,
                send_admin_error,
                send_user_friendly_error,
                send_fallback_image,
                result,
            )

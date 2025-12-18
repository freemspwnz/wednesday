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
from utils.chats_store import ChatsStore
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
        chats: ChatsStore,
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
        result: DispatchResult = DispatchResult(
            slot_date=slot_date,
            slot_time=slot_time,
            total_targets=0,
            success_count=0,
            failed_count=0,
            used_fallback=False,
        )

        try:
            # Сначала соберём список целевых чатов
            targets: set[int] = set(await self._chats.list_chat_ids() or [])
            if main_chat_id:
                try:
                    chat_id_int: int = int(str(main_chat_id))
                    targets.add(chat_id_int)
                except (ValueError, TypeError):
                    pass

            result["total_targets"] = len(targets)

            # Если нет ни одного чата — просто выходим
            if not targets:
                self.logger.warning("Нет целевых чатов для отправки сообщения")
                await send_error_message("Нет настроенных чатов для отправки")
                return result

            # Проверяем, отправляли ли уже в этот слот во ВСЕ целевые чаты
            already_dispatched_for_all = True
            for target_chat in targets:
                if not await self._dispatch_registry.is_dispatched(
                    slot_date,
                    slot_time,
                    target_chat,
                ):
                    already_dispatched_for_all = False
                    break

            if already_dispatched_for_all:
                self.logger.info(
                    "Уже отправлено ранее для всех чатов в слот %s_%s. Пропускаю генерацию.",
                    slot_date,
                    slot_time,
                )
                return result

            # Генерируем изображение жабы только если есть хотя бы один чат без отправки
            if self._image_service is None:
                self.logger.error("ImageService недоступен, пропускаю генерацию")
                return result

            generation_result = await self._image_service.generate_frog_image()

            if generation_result:
                image_data, caption = generation_result

                for target_chat in targets:
                    # Проверяем, не было ли уже отправлено в этот чат в этот тайм-слот
                    if await self._dispatch_registry.is_dispatched(
                        slot_date,
                        slot_time,
                        target_chat,
                    ):
                        self.logger.info(
                            "Пропускаем отправку в %s - уже отправлено в слот %s_%s",
                            target_chat,
                            slot_date,
                            slot_time,
                        )
                        continue

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
                        self.logger.info("Жаба отправлена в чат %s", target_chat)
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
                            "Неожиданная программная ошибка при отправке изображения в чат %s: %s",
                            target_chat,
                            send_error,
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

                return result

            # Если генерация не удалась, отправляем сообщения об ошибке и fallback
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

            for target_chat in targets:
                try:
                    # Проверяем, не было ли уже отправлено в этот чат в этот тайм-слот
                    if await self._dispatch_registry.is_dispatched(
                        slot_date,
                        slot_time,
                        target_chat,
                    ):
                        self.logger.info(
                            "Пропускаем fallback отправку в %s - уже отправлено в слот %s_%s",
                            target_chat,
                            slot_date,
                            slot_time,
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
                    self.logger.error("Ошибка при отправке fallback в чат %s: %s", target_chat, send_error)
                    result["failed_count"] += 1

            return result

        except Exception as e:
            error_details = f"Произошла ошибка при отправке жабы: {e!s}"
            self.logger.error(error_details, exc_info=True)

            # Отправляем детальное сообщение администратору с трейcом
            import traceback

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

            for target_chat in targets:
                try:
                    # Проверяем, не было ли уже отправлено в этот чат в этот тайм-слот
                    if await self._dispatch_registry.is_dispatched(
                        slot_date,
                        slot_time,
                        target_chat,
                    ):
                        self.logger.info(
                            "Пропускаем fallback отправку в %s - уже отправлено в слот %s_%s",
                            target_chat,
                            slot_date,
                            slot_time,
                        )
                        continue

                    # Отправляем дружелюбное сообщение
                    await send_user_friendly_error(target_chat)

                    # Отправляем случайное изображение
                    if await send_fallback_image(target_chat):
                        try:
                            await self._metrics.increment_dispatch_success()
                        except Exception:  # pragma: no cover
                            pass
                        result["success_count"] += 1
                except Exception as send_error:
                    self.logger.error("Ошибка при отправке fallback в чат %s: %s", target_chat, send_error)
                    result["failed_count"] += 1

            return result

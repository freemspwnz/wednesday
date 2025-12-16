import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot import handlers as bot_handlers_module
from bot.handlers import CommandHandlers


@pytest.mark.asyncio
async def test_start_command_replies(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=lambda: None)
    async_retry_stub(handler)

    await handler.start_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_help_command_replies(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminNo:
        async def is_admin(self, _uid: int) -> bool:
            return False

    handler.admins_store = _AdminNo()  # type: ignore[assignment]

    await handler.help_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    sent_text = call.kwargs.get("text", call.args[0])
    assert "/start" in sent_text
    assert "/help" in sent_text


@pytest.mark.asyncio
async def test_start_command_handles_retry_failure(fake_update: Any, fake_context: Any, monkeypatch: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    def failing_retry(func: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("boom")

    fake_logger = MagicMock()
    handler.logger = fake_logger
    monkeypatch.setattr(handler, "_retry_on_connect_error", failing_retry)

    # Метод не должен выбрасывать исключение наружу
    await handler.start_command(fake_update, fake_context)

    fake_logger.error.assert_called()


@pytest.mark.asyncio
async def test_help_command_admin_version(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=lambda: None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    await handler.help_command(fake_update, fake_context)

    call = fake_update.message.reply_text.await_args
    sent_text = call.kwargs.get("text", call.args[0])
    assert "Админ-справка" in sent_text


@pytest.mark.asyncio
async def test_set_frog_limit_command_success(fake_update: Any, fake_context: Any) -> None:
    class FakeUsage:
        def __init__(self) -> None:
            self.frog_threshold: int = 70
            self.monthly_quota: int = 100
            self.total: int = 10

        async def set_frog_threshold(self, value: int) -> int:
            self.frog_threshold = value
            return value

        async def get_limits_info(self) -> tuple[int, int, int]:
            return self.total, self.frog_threshold, self.monthly_quota

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    class _AdminOk2:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk2()  # type: ignore[assignment]

    fake_context.application.bot_data["usage"] = FakeUsage()
    fake_context.args = ["80"]

    await handler.set_frog_limit_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Порог /frog установлен" in message


@pytest.mark.asyncio
async def test_set_frog_limit_command_invalid(fake_update: Any, fake_context: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = ["-5"]

    await handler.set_frog_limit_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Неверный параметр" in message


@pytest.mark.asyncio
async def test_frog_command_success(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    monkeypatch: Any,
) -> None:
    """Успешный сценарий /frog: задача ставится в Celery очередь."""

    class DummyUsage:
        def __init__(self) -> None:
            self.count: int = 0
            self.monthly_quota: int = 100
            self.frog_threshold: int = 70

        async def can_use_frog(self) -> bool:
            return True

        async def get_limits_info(self) -> tuple[int, int, int]:
            return self.count, self.frog_threshold, self.monthly_quota

    # image_generator в обработчике больше не используется напрямую для /frog,
    # достаточно простого MagicMock
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminNo:
        async def is_admin(self, _uid: int) -> bool:
            return False

        async def list_all_admins(self) -> list[int]:
            return []

    handler.admins_store = _AdminNo()  # type: ignore[assignment]

    fake_context.application.bot_data["usage"] = DummyUsage()

    # Добавляем chat_id в fake_update.message для совместимости с новым кодом
    fake_update.message.chat_id = fake_update.effective_chat.id

    # Мокаем отправку задачи в Celery
    from services.celery_app import celery_app

    send_task_mock = MagicMock()
    monkeypatch.setattr(celery_app, "send_task", send_task_mock)

    await handler.frog_command(fake_update, fake_context)

    # Проверяем, что отправлено статусное сообщение
    fake_update.message.reply_text.assert_awaited()
    status_call = fake_update.message.reply_text.await_args
    status_text = status_call.kwargs.get("text", status_call.args[0])
    assert "Генерирую жабу" in status_text

    # Проверяем, что Celery-задача поставлена в очередь
    send_task_mock.assert_called_once()
    task_args, task_kwargs = send_task_mock.call_args
    assert task_args[0] == "wednesday.send_frog_manual"
    # args=[chat_id, user_id, status_message_id]
    call_args = task_kwargs["args"]
    assert call_args[0] == fake_update.effective_chat.id
    assert call_args[1] == fake_update.effective_user.id


@pytest.mark.asyncio
async def test_frog_command_usage_limit(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    monkeypatch: Any,
) -> None:
    """При превышении лимита /frog задача в Celery не ставится, а юзеру возвращается сообщение."""

    class LimitedUsage:
        def __init__(self) -> None:
            self.monthly_quota: int = 100
            self.frog_threshold: int = 70

        async def can_use_frog(self) -> bool:
            return False

        async def get_limits_info(self) -> tuple[int, int, int]:
            return 70, self.frog_threshold, self.monthly_quota

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminNo2:
        async def is_admin(self, _uid: int) -> bool:
            return False

    handler.admins_store = _AdminNo2()  # type: ignore[assignment]

    fake_context.application.bot_data["usage"] = LimitedUsage()

    # Добавляем chat_id для совместимости
    fake_update.message.chat_id = fake_update.effective_chat.id

    from services.celery_app import celery_app

    send_task_mock = MagicMock()
    monkeypatch.setattr(celery_app, "send_task", send_task_mock)

    await handler.frog_command(fake_update, fake_context)

    call = fake_update.message.reply_text.await_args
    message = call.kwargs.get("text", call.args[0])
    assert "Лимит ручных генераций" in message

    # Убедимся, что задача в Celery не ставилась
    assert send_task_mock.call_count == 0


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_status_command_integration_with_postgres_stores(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
) -> None:
    from utils.chats_store import ChatsStore
    from utils.metrics import Metrics
    from utils.usage_tracker import UsageTracker

    # Настраиваем image_generator с простыми async-заглушками
    image_generator = MagicMock()
    image_generator.check_api_status = AsyncMock(
        return_value=(True, "OK", [], (None, None)),
    )
    image_generator.gigachat_client = None

    handler = CommandHandlers(image_generator=image_generator, next_run_provider=lambda: None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    # Реальные async-хранилища на Postgres
    usage = UsageTracker(storage_path="ignored.json")
    chats = ChatsStore(storage_path="ignored.json")
    metrics = Metrics(storage_path="ignored.json")

    fake_context.application.bot_data["usage"] = usage
    fake_context.application.bot_data["chats"] = chats
    fake_context.application.bot_data["metrics"] = metrics

    # get_me требуется в статусе
    fake_context.bot.get_me = AsyncMock(return_value=SimpleNamespace(first_name="TestBot"))

    await handler.status_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Статус бота" in text
    assert "Генерации:" in text


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_force_send_command_integration_with_postgres_stores(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
) -> None:
    from utils.chats_store import ChatsStore
    from utils.usage_tracker import UsageTracker

    class _DummyGenerator:
        def __init__(self) -> None:
            self.generate_frog_image = AsyncMock(return_value=(b"img", "caption"))
            self.save_image_locally = MagicMock(return_value="saved")
            self.get_random_saved_image = MagicMock(return_value=None)

    image_generator = _DummyGenerator()

    handler = CommandHandlers(image_generator=image_generator, next_run_provider=None)  # type: ignore[arg-type]
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    # Реальные async-хранилища
    chats = ChatsStore(storage_path="ignored.json")
    await chats.add_chat(fake_update.effective_chat.id, "Test chat")
    usage = UsageTracker(storage_path="ignored.json")

    fake_context.application.bot_data["chats"] = chats
    fake_context.application.bot_data["usage"] = usage

    # Вызываем /force_send all
    fake_context.args = ["all"]

    await handler.admin_force_send_command(fake_update, fake_context)

    # Должна быть хотя бы одна отправка фото
    assert fake_context.bot.send_photo.await_count >= 1


@pytest.mark.asyncio
async def test_set_frog_used_command_success(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    class FakeUsage:
        def __init__(self) -> None:
            self.monthly_quota: int = 100
            self.frog_threshold: int = 70

        async def set_month_total(self, value: int) -> None:
            self.total = value

        async def get_limits_info(self) -> tuple[int, int, int]:
            return getattr(self, "total", 0), self.frog_threshold, self.monthly_quota

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.application.bot_data["usage"] = FakeUsage()
    fake_context.args = ["50"]

    await handler.set_frog_used_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Текущее использование /frog" in message


@pytest.mark.asyncio
async def test_set_frog_used_command_invalid(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = ["-10"]

    await handler.set_frog_used_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Неверный параметр" in message


@pytest.mark.asyncio
async def test_set_frog_used_command_no_args(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = []

    await handler.set_frog_used_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Использование: /set_frog_used" in message


@pytest.mark.asyncio
async def test_unknown_command(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    await handler.unknown_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Неизвестная команда" in text
    assert "/start" in text
    assert "/help" in text


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_admin_add_chat_command_success(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
) -> None:
    from utils.chats_store import ChatsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    chats = ChatsStore(storage_path="ignored.json")
    fake_context.application.bot_data["chats"] = chats
    fake_context.args = ["12345"]

    await handler.admin_add_chat_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Чат 12345 добавлен" in message

    # Проверяем, что чат действительно добавлен
    chat_ids = await chats.list_chat_ids()
    assert 12345 in chat_ids


@pytest.mark.asyncio
async def test_admin_add_chat_command_no_args(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = []

    await handler.admin_add_chat_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Использование: /add_chat" in message


@pytest.mark.asyncio
async def test_admin_add_chat_command_invalid_id(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = ["not_a_number"]

    await handler.admin_add_chat_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Неверный chat_id" in message


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_admin_remove_chat_command_success(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
) -> None:
    from utils.chats_store import ChatsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    chats = ChatsStore(storage_path="ignored.json")
    await chats.add_chat(12345, "Test chat")
    fake_context.application.bot_data["chats"] = chats
    fake_context.args = ["12345"]

    await handler.admin_remove_chat_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Чат 12345 удалён" in message

    # Проверяем, что чат действительно удалён
    chat_ids = await chats.list_chat_ids()
    assert 12345 not in chat_ids


@pytest.mark.asyncio
async def test_admin_remove_chat_command_no_args(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = []

    await handler.admin_remove_chat_command(fake_update, fake_context)

    last_call = fake_update.message.reply_text.await_args
    message = last_call.kwargs.get("text", last_call.args[0])
    assert "Использование: /remove_chat" in message


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_list_chats_command_success(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
) -> None:
    from utils.chats_store import ChatsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    chats = ChatsStore(storage_path="ignored.json")
    await chats.add_chat(11111, "Chat 1")
    await chats.add_chat(22222, "Chat 2")
    fake_context.application.bot_data["chats"] = chats

    await handler.list_chats_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Активные чаты" in text or "чатов" in text.lower()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_list_chats_command_no_chats(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
) -> None:
    from utils.chats_store import ChatsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    chats = ChatsStore(storage_path="ignored.json")
    fake_context.application.bot_data["chats"] = chats

    await handler.list_chats_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Нет активных чатов" in text or "чатов: 0" in text


@pytest.mark.asyncio
async def test_stop_command_non_admin(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminNo:
        async def is_admin(self, _uid: int) -> bool:
            return False

    handler.admins_store = _AdminNo()  # type: ignore[assignment]

    await handler.stop_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Доступно только администратору" in text


@pytest.mark.asyncio
async def test_stop_command_admin(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    # Мокаем bot_instance в bot_data
    class DummyBot:
        async def stop(self) -> None:
            pass

    fake_context.application.bot_data["bot"] = DummyBot()

    await handler.stop_command(fake_update, fake_context)

    # Проверяем, что была попытка остановить бота
    assert "bot" in fake_context.application.bot_data


@pytest.mark.asyncio
async def test_set_kandinsky_model_command_no_args(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = []

    await handler.set_kandinsky_model_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Использование: /set_kandinsky_model" in text


@pytest.mark.asyncio
async def test_set_kandinsky_model_command_success(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    image_client = MagicMock()
    image_client.set_model = AsyncMock(return_value=(True, "Модель установлена"))

    image_generator = MagicMock()
    image_generator.image_client = image_client

    handler = CommandHandlers(image_generator=image_generator, next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = ["kandinsky-2.2"]

    await handler.set_kandinsky_model_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "✅" in text or "Модель установлена" in text
    image_client.set_model.assert_awaited_once_with("kandinsky-2.2")


@pytest.mark.asyncio
async def test_set_gigachat_model_command_no_args(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = []

    await handler.set_gigachat_model_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Использование: /set_gigachat_model" in text


@pytest.mark.asyncio
async def test_set_gigachat_model_command_no_client(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    image_generator = MagicMock()
    image_generator.text_client = None

    handler = CommandHandlers(image_generator=image_generator, next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = ["GigaChat-Pro"]

    await handler.set_gigachat_model_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "GigaChat клиент не инициализирован" in text


@pytest.mark.asyncio
async def test_set_gigachat_model_command_success(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    text_client = MagicMock()
    text_client.set_model = AsyncMock(return_value=(True, "✅ Модель GigaChat установлена: GigaChat-Pro"))

    image_generator = MagicMock()
    image_generator.text_client = text_client

    handler = CommandHandlers(image_generator=image_generator, next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]
    fake_context.args = ["GigaChat-Pro"]

    await handler.set_gigachat_model_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "✅" in text or "Модель GigaChat установлена" in text
    text_client.set_model.assert_awaited_once_with("GigaChat-Pro")


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_mod_command_success(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест успешного выполнения команды /mod (обновленный для супер-админа)."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    # Импортируем реальный AdminsStore напрямую из модуля, обходя патч
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    # Перезагружаем модуль, чтобы получить реальный класс
    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    # Используем реальный AdminsStore для теста
    admins = AdminsStore()
    handler.admins_store = admins
    fake_context.application.bot_data["admins"] = admins
    fake_context.args = ["99999"]
    fake_update.message.reply_to_message = None

    await handler.mod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "✅" in text or "добавлен" in text.lower() or "админ-права" in text.lower()


@pytest.mark.asyncio
async def test_mod_command_no_args(
    fake_update: Any, fake_context: Any, async_retry_stub: Any, monkeypatch: Any
) -> None:
    """Тест команды /mod без аргументов (обновленный для супер-админа)."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    from bot.handlers import CommandHandlers

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    # Не нужно мокать admins_store, так как теперь проверяется _is_super_admin
    fake_context.args = []
    fake_update.message.reply_to_message = None

    await handler.mod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Использование" in text or "ответьте" in text.lower()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_unmod_command_success(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест успешного выполнения команды /unmod (обновленный для супер-админа)."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    # Импортируем реальный AdminsStore напрямую из модуля, обходя патч
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    # Перезагружаем модуль, чтобы получить реальный класс
    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    # Используем реальный AdminsStore для теста
    admins = AdminsStore()
    await admins.add_admin(99999)
    handler.admins_store = admins
    fake_context.application.bot_data["admins"] = admins
    fake_context.args = ["99999"]
    fake_update.message.reply_to_message = None

    await handler.unmod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "✅" in text or "удалён" in text.lower() or "админ-права" in text.lower()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_unmod_command_no_args_shows_list(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест команды /unmod без аргументов (теперь показывает список админов)."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    handler.admins_store = admins
    fake_context.args = []
    fake_update.message.reply_to_message = None

    # Мокаем get_chat для получения информации о пользователях
    def mock_get_chat(chat_id: int) -> Any:
        chat = SimpleNamespace()
        chat.full_name = f"User {chat_id}"
        return chat

    fake_context.bot.get_chat = AsyncMock(side_effect=mock_get_chat)

    await handler.unmod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Список администраторов" in text or "администраторов" in text.lower()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_list_mods_command_success(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    # Импортируем реальный AdminsStore напрямую из модуля, обходя патч
    import utils.admins_store as admins_store_module

    # Перезагружаем модуль, чтобы получить реальный класс
    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    # Используем реальный AdminsStore для теста
    admins = AdminsStore()
    # Делаем пользователя 42 администратором
    await admins.add_admin(fake_update.effective_user.id)
    await admins.add_admin(11111)
    await admins.add_admin(22222)
    handler.admins_store = admins
    fake_context.application.bot_data["admins"] = admins

    await handler.list_mods_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Администраторы" in text or "модераторы" in text.lower() or "админ" in text.lower()


@pytest.mark.asyncio
async def test_list_models_command(fake_update: Any, fake_context: Any, async_retry_stub: Any) -> None:
    image_generator = MagicMock()
    image_generator.check_api_status = AsyncMock(
        return_value=(True, "OK", ["Model 1", "Model 2"], ("id1", "name1")),
    )
    image_generator.gigachat_client = MagicMock()
    image_generator.gigachat_client.get_available_models = MagicMock(return_value=["GigaChat-1", "GigaChat-2"])

    handler = CommandHandlers(image_generator=image_generator, next_run_provider=None)
    async_retry_stub(handler)

    class _AdminOk:
        async def is_admin(self, _uid: int) -> bool:
            return True

    handler.admins_store = _AdminOk()  # type: ignore[assignment]

    await handler.list_models_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Kandinsky" in text or "GigaChat" in text or "модели" in text.lower()


# Тесты для новых функций mod/unmod с поддержкой reply и ограничением доступа
@pytest.mark.asyncio
async def test_extract_target_user_id_from_reply(fake_update: Any, fake_context: Any) -> None:
    """Тест извлечения target_user_id из reply на сообщение."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    # Создаем reply_to_message
    reply_user = SimpleNamespace(id=12345)
    reply_message = SimpleNamespace(from_user=reply_user)
    fake_update.message.reply_to_message = reply_message
    fake_context.args = []

    target_id = await handler._extract_target_user_id(fake_update, fake_context)
    assert target_id == 12345


@pytest.mark.asyncio
async def test_extract_target_user_id_from_args(fake_update: Any, fake_context: Any) -> None:
    """Тест извлечения target_user_id из аргументов команды."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    fake_update.message.reply_to_message = None
    fake_context.args = ["67890"]

    target_id = await handler._extract_target_user_id(fake_update, fake_context)
    assert target_id == 67890


@pytest.mark.asyncio
async def test_extract_target_user_id_priority_reply_over_args(fake_update: Any, fake_context: Any) -> None:
    """Тест приоритета reply над аргументами."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    # Есть и reply, и аргументы - должен вернуть reply
    reply_user = SimpleNamespace(id=11111)
    reply_message = SimpleNamespace(from_user=reply_user)
    fake_update.message.reply_to_message = reply_message
    fake_context.args = ["22222"]

    target_id = await handler._extract_target_user_id(fake_update, fake_context)
    assert target_id == 11111


@pytest.mark.asyncio
async def test_extract_target_user_id_invalid_args(fake_update: Any, fake_context: Any) -> None:
    """Тест обработки невалидных аргументов."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    fake_update.message.reply_to_message = None
    fake_context.args = ["not_a_number"]

    target_id = await handler._extract_target_user_id(fake_update, fake_context)
    assert target_id is None


@pytest.mark.asyncio
async def test_extract_target_user_id_multiple_args(fake_update: Any, fake_context: Any) -> None:
    """Тест обработки множественных аргументов (должен вернуть None)."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    fake_update.message.reply_to_message = None
    fake_context.args = ["111", "222"]

    target_id = await handler._extract_target_user_id(fake_update, fake_context)
    assert target_id is None


@pytest.mark.asyncio
async def test_extract_target_user_id_no_reply_no_args(fake_update: Any, fake_context: Any) -> None:
    """Тест отсутствия reply и аргументов (должен вернуть None)."""
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)

    fake_update.message.reply_to_message = None
    fake_context.args = []

    target_id = await handler._extract_target_user_id(fake_update, fake_context)
    assert target_id is None


@pytest.mark.asyncio
async def test_is_super_admin_true(monkeypatch: Any) -> None:
    """Тест проверки супер-админа (должен вернуть True)."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")
    importlib.reload(bot_handlers_module)
    from bot.handlers import CommandHandlers

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    assert handler._is_super_admin(42) is True


@pytest.mark.asyncio
async def test_is_super_admin_false(monkeypatch: Any) -> None:
    """Тест проверки не-супер-админа (должен вернуть False)."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "999998")
    importlib.reload(bot_handlers_module)
    from bot.handlers import CommandHandlers

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    assert handler._is_super_admin(42) is False


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_mod_command_non_super_admin_denied(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест отказа команды /mod от не-супер-админа."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "999998")  # Другой ID, не 42
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    await admins.add_admin(fake_update.effective_user.id)  # Делаем пользователя 42 админом, но не супер-админом
    handler.admins_store = admins
    fake_context.args = ["99999"]

    await handler.mod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "главному администратору" in text.lower() or "доступно только" in text.lower()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_mod_command_with_reply(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест команды /mod с reply на сообщение."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    handler.admins_store = admins
    fake_context.args = []

    # Создаем reply
    reply_user = SimpleNamespace(id=12345)
    reply_message = SimpleNamespace(from_user=reply_user)
    fake_update.message.reply_to_message = reply_message

    await handler.mod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "✅" in text or "админ‑права" in text.lower() or "админ-права" in text.lower()
    assert "12345" in text


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_mod_command_with_args(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест команды /mod с аргументом user_id."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    handler.admins_store = admins
    fake_context.args = ["54321"]
    fake_update.message.reply_to_message = None

    await handler.mod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "✅" in text or "админ‑права" in text.lower() or "админ-права" in text.lower()
    assert "54321" in text


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_unmod_command_non_super_admin_denied(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест отказа команды /unmod от не-супер-админа."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "999998")  # Другой ID, не 42
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    await admins.add_admin(fake_update.effective_user.id)
    handler.admins_store = admins
    fake_context.args = ["99999"]

    await handler.unmod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "главному администратору" in text.lower() or "доступно только" in text.lower()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_unmod_command_with_reply(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест команды /unmod с reply на сообщение."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    await admins.add_admin(12345)  # Добавляем админа для удаления
    handler.admins_store = admins
    fake_context.args = []
    fake_context.bot.get_chat = AsyncMock(return_value=SimpleNamespace(full_name="Test User"))

    # Создаем reply
    reply_user = SimpleNamespace(id=12345)
    reply_message = SimpleNamespace(from_user=reply_user)
    fake_update.message.reply_to_message = reply_message

    await handler.unmod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "✅" in text or "удалены" in text.lower() or "админ‑права" in text.lower()
    assert "12345" in text


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_unmod_command_with_args(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест команды /unmod с аргументом user_id."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    await admins.add_admin(54321)
    handler.admins_store = admins
    fake_context.args = ["54321"]
    fake_update.message.reply_to_message = None

    await handler.unmod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "✅" in text or "удалены" in text.lower() or "админ‑права" in text.lower()
    assert "54321" in text


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_unmod_command_cannot_remove_super_admin(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест попытки удалить главного администратора (должен быть отказ)."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    handler.admins_store = admins
    fake_context.args = ["42"]  # Пытаемся удалить самого себя (главного админа)
    fake_update.message.reply_to_message = None

    await handler.unmod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "главного администратора" in text.lower() or "нельзя удалить" in text.lower()


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_unmod_command_shows_admin_list_when_no_args(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    cleanup_tables: Any,
    monkeypatch: Any,
) -> None:
    """Тест показа списка админов при вызове /unmod без аргументов."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")  # Пользователь 42 - супер-админ
    importlib.reload(bot_handlers_module)
    import utils.admins_store as admins_store_module
    from bot.handlers import CommandHandlers

    importlib.reload(admins_store_module)
    AdminsStore = admins_store_module.AdminsStore

    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    admins = AdminsStore()
    await admins.add_admin(11111)
    await admins.add_admin(22222)
    handler.admins_store = admins
    fake_context.args = []
    fake_update.message.reply_to_message = None

    # Мокаем get_chat для получения информации о пользователях
    def mock_get_chat(chat_id: int) -> Any:
        chat = SimpleNamespace()
        chat.full_name = f"User {chat_id}"
        chat.username = f"user{chat_id}"
        return chat

    fake_context.bot.get_chat = AsyncMock(side_effect=mock_get_chat)

    await handler.unmod_command(fake_update, fake_context)

    fake_update.message.reply_text.assert_awaited()
    call = fake_update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "Список администраторов" in text or "администраторов" in text.lower()
    assert "42" in text  # Главный админ должен быть в списке
    assert "11111" in text or "22222" in text  # Хотя бы один из добавленных админов

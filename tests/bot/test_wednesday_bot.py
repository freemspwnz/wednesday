from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Константы для тестов
EXPECTED_SEND_COUNT = 2
EXPECTED_HANDLERS_COUNT = 20


@pytest.fixture
def wednesday_bot(monkeypatch: Any) -> Any:
    from bot import wednesday_bot as wb_module

    class DummyApplication:
        def __init__(self) -> None:
            self.added_handlers: list[Any] = []
            self.bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
            self.bot_data: dict[str, Any] = {}
            self.updater = SimpleNamespace(stop=AsyncMock())

        def add_handler(self, handler: Any) -> None:
            self.added_handlers.append(handler)

    def builder_factory() -> Any:
        app_instance = DummyApplication()

        class Builder:
            def __init__(self) -> None:
                self._token: Any = None
                self._request: Any = None

            def token(self, token: str) -> "Builder":
                self._token = token
                return self

            def request(self, request: Any) -> "Builder":
                self._request = request
                return self

            def build(self) -> DummyApplication:
                return app_instance

        return Builder()

    def app_builder() -> Any:
        return builder_factory()

    monkeypatch.setattr(wb_module, "Application", SimpleNamespace(builder=app_builder))

    def http_request(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(wb_module, "HTTPXRequest", http_request)

    class DummyImageService:
        def __init__(self) -> None:
            self.saved: list[Any] = []

        async def generate_frog_image(self, user_id: int | None = None) -> tuple[bytes, str]:
            return b"img", "caption"

    class DummyUsageTracker:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.total: int = 0

        async def increment(self, value: int) -> None:
            self.total += value

    class DummyChatsRepo:
        def __init__(self) -> None:
            self.chat_ids: list[int] = [111]

        async def list_chat_ids(self) -> list[int]:
            return list(self.chat_ids)

        async def add_chat(self, chat_id: int, title: str) -> None:
            if chat_id not in self.chat_ids:
                self.chat_ids.append(chat_id)

        async def remove_chat(self, chat_id: int) -> None:
            if chat_id in self.chat_ids:
                self.chat_ids.remove(chat_id)

    class DummyDispatchRegistry:
        def __init__(self) -> None:
            self.sent: set[Any] = set()

        async def is_dispatched(self, date: str, slot: str, chat_id: int) -> bool:
            return (date, slot, chat_id) in self.sent

        async def mark_dispatched(self, date: str, slot: str, chat_id: int) -> None:
            self.sent.add((date, slot, chat_id))

    class DummyMetrics:
        def __init__(self) -> None:
            self.success: int = 0
            self.failed: int = 0

        async def increment_dispatch_success(self) -> None:
            self.success += 1

        async def increment_dispatch_failed(self) -> None:
            self.failed += 1

    class DummyCommandHandler:
        def __init__(self, command: Any, callback: Any) -> None:
            self.command = command
            self.callback = callback

    class DummyMessageHandler:
        def __init__(self, command_filter: Any, callback: Any) -> None:
            self.command_filter = command_filter
            self.callback = callback

    class DummyChatMemberHandler:
        MY_CHAT_MEMBER = object()

        def __init__(self, callback: Any, member_filter: Any) -> None:
            self.callback = callback
            self.member_filter = member_filter

    # Создаём mock-сервисы для передачи в конструктор
    mock_services = SimpleNamespace(
        image_service=DummyImageService(),
        usage=DummyUsageTracker(),
        chats=DummyChatsRepo(),
        dispatch_registry=DummyDispatchRegistry(),
        metrics=DummyMetrics(),
        settings=SimpleNamespace(scheduler_send_times=["10:00"], time_format_length=5),
        frog_rate_limiter=SimpleNamespace(),
        task_queue=SimpleNamespace(),
        bot_controller=None,
    )

    monkeypatch.setattr(wb_module, "CommandHandler", DummyCommandHandler)
    monkeypatch.setattr(wb_module, "MessageHandler", DummyMessageHandler)
    monkeypatch.setattr(wb_module, "ChatMemberHandler", DummyChatMemberHandler)
    monkeypatch.setattr(wb_module, "filters", SimpleNamespace(COMMAND="COMMAND"))

    # Создаём мок конфигурации для тестов
    from shared.config import BotTelegramConfig

    telegram_config = BotTelegramConfig(bot_token="test_token", chat_id="123")

    # Создаём бот с внедрёнными сервисами через DI
    bot = wb_module.WednesdayBot(services=mock_services, telegram_config=telegram_config)  # type: ignore[arg-type]
    return bot


def test_wednesday_bot_initializes_components(wednesday_bot: Any) -> None:
    assert wednesday_bot.application is not None
    assert wednesday_bot.user_handlers is not None
    assert wednesday_bot.admin_handlers is not None
    assert wednesday_bot.model_handlers is not None
    assert wednesday_bot.is_running is False


def test_setup_handlers_registers_all_callbacks(wednesday_bot: Any) -> None:
    wednesday_bot.setup_handlers()
    assert len(wednesday_bot.application.added_handlers) == EXPECTED_HANDLERS_COUNT


@pytest.mark.asyncio
async def test_send_wednesday_frog_dispatches_to_targets(monkeypatch: Any, wednesday_bot: Any) -> None:
    wednesday_bot.chat_id = "222"
    wednesday_bot.chats.chat_ids = [111]

    def fake_generate(metrics: Any = None) -> tuple[bytes, str]:
        return b"img", "caption"

    wednesday_bot.services.image_service.generate_frog_image = AsyncMock(side_effect=fake_generate)

    await wednesday_bot.send_wednesday_frog(slot_time="10:00")

    assert wednesday_bot.application.bot.send_photo.await_count == EXPECTED_SEND_COUNT
    assert wednesday_bot.usage.total == EXPECTED_SEND_COUNT
    assert wednesday_bot.metrics.success == EXPECTED_SEND_COUNT


@pytest.mark.asyncio
async def test_send_wednesday_frog_without_targets(monkeypatch: Any, wednesday_bot: Any) -> None:
    wednesday_bot.chat_id = None
    wednesday_bot.chats.chat_ids = []
    wednesday_bot._send_error_message = AsyncMock()

    await wednesday_bot.send_wednesday_frog(slot_time="10:00")

    wednesday_bot._send_error_message.assert_awaited_once()
    assert wednesday_bot.application.bot.send_photo.await_count == 0


@pytest.mark.asyncio
async def test_send_error_message(wednesday_bot: Any) -> None:
    wednesday_bot.chat_id = "12345"
    await wednesday_bot._send_error_message("Test error")

    wednesday_bot.application.bot.send_message.assert_awaited_once()
    call = wednesday_bot.application.bot.send_message.await_args
    assert call.kwargs["chat_id"] == "12345"
    assert "Test error" in call.kwargs["text"]


@pytest.mark.asyncio
async def test_send_user_friendly_error(wednesday_bot: Any) -> None:
    await wednesday_bot._send_user_friendly_error(12345, "test context")

    wednesday_bot.application.bot.send_message.assert_awaited_once()
    call = wednesday_bot.application.bot.send_message.await_args
    assert call.kwargs["chat_id"] == 12345
    assert "не удалось сгенерировать" in call.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_send_fallback_image_success(wednesday_bot: Any) -> None:
    storage = MagicMock()
    storage.get_random_from_archive.return_value = (b"img", "caption")
    image_service = wednesday_bot.services.image_service
    image_service._storage = storage
    result = await wednesday_bot._send_fallback_image(12345)

    assert result is True
    wednesday_bot.application.bot.send_photo.assert_awaited_once()
    call = wednesday_bot.application.bot.send_photo.await_args
    assert call.kwargs["chat_id"] == 12345


@pytest.mark.asyncio
async def test_send_fallback_image_no_image(wednesday_bot: Any) -> None:
    storage = MagicMock()
    storage.get_random_from_archive.return_value = None
    image_service = wednesday_bot.services.image_service
    image_service._storage = storage
    result = await wednesday_bot._send_fallback_image(12345)

    assert result is False
    assert wednesday_bot.application.bot.send_photo.await_count == 0


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_on_my_chat_member_added(wednesday_bot: Any, cleanup_tables: Any) -> None:
    from types import SimpleNamespace

    old_member = SimpleNamespace(status="left")
    new_member = SimpleNamespace(status="member")
    chat = SimpleNamespace(id=99999, title="Test Chat", username="")
    my_chat_member = SimpleNamespace(
        old_chat_member=old_member,
        new_chat_member=new_member,
        chat=chat,
    )
    update = SimpleNamespace(my_chat_member=my_chat_member)

    await wednesday_bot.on_my_chat_member(update, SimpleNamespace())

    # Проверяем, что чат добавлен
    chat_ids = await wednesday_bot.chats.list_chat_ids()
    assert 99999 in chat_ids
    # Проверяем, что было отправлено приветствие (может быть несколько вызовов)
    assert wednesday_bot.application.bot.send_message.await_count >= 1


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.usefixtures("_setup_test_postgres")
@pytest.mark.asyncio
async def test_on_my_chat_member_removed(wednesday_bot: Any, cleanup_tables: Any) -> None:
    from types import SimpleNamespace

    # Сначала добавляем чат
    await wednesday_bot.chats.add_chat(99999, "Test Chat")

    old_member = SimpleNamespace(status="member")
    new_member = SimpleNamespace(status="left")
    chat = SimpleNamespace(id=99999, title="Test Chat", username="")
    my_chat_member = SimpleNamespace(
        old_chat_member=old_member,
        new_chat_member=new_member,
        chat=chat,
    )
    update = SimpleNamespace(my_chat_member=my_chat_member)

    await wednesday_bot.on_my_chat_member(update, SimpleNamespace())

    # Проверяем, что чат удалён
    chat_ids = await wednesday_bot.chats.list_chat_ids()
    assert 99999 not in chat_ids


@pytest.mark.asyncio
async def test_stop_bot(wednesday_bot: Any) -> None:
    wednesday_bot.is_running = True

    await wednesday_bot.stop()

    assert wednesday_bot.is_running is False
    wednesday_bot.application.updater.stop.assert_awaited()


@pytest.mark.asyncio
async def test_stop_bot_already_stopped(wednesday_bot: Any) -> None:
    wednesday_bot.is_running = False

    await wednesday_bot.stop()

    # Не должно быть попыток остановки
    assert wednesday_bot.is_running is False

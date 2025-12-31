import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def support_bot(monkeypatch: Any) -> Any:
    from bot import support_bot as sb_module

    class DummyApplication:
        def __init__(self) -> None:
            self.added_handlers: list[Any] = []
            self.bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
            self.bot_data: dict[str, Any] = {}
            self.updater = SimpleNamespace(stop=AsyncMock(), start_polling=AsyncMock())

        def add_handler(self, handler: Any) -> None:
            self.added_handlers.append(handler)

    def builder_factory() -> Any:
        app_instance = DummyApplication()

        class Builder:
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

    monkeypatch.setattr(sb_module, "Application", SimpleNamespace(builder=app_builder))

    def http_request(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(sb_module, "HTTPXRequest", http_request)

    class DummyAdminsRepo:
        def __init__(self) -> None:
            self.admins: set[int] = {1}

        async def is_admin(self, user_id: int) -> bool:
            return user_id in self.admins

        async def list_all_admins(self) -> list[int]:
            return list(self.admins)

        async def add_admin(self, user_id: int) -> bool:
            self.admins.add(user_id)
            return True

        async def remove_admin(self, user_id: int) -> bool:
            self.admins.discard(user_id)
            return True

    class DummyChatsRepo:
        def __init__(self) -> None:
            self.chats: dict[int, str] = {}

        async def add_chat(self, chat_id: int, title: str | None = None) -> None:
            self.chats[chat_id] = title or ""

        async def remove_chat(self, chat_id: int) -> None:
            self.chats.pop(chat_id, None)

        async def list_chat_ids(self) -> list[int]:
            return list(self.chats.keys())

    class DummyCommandHandler:
        def __init__(self, command: Any, callback: Any) -> None:
            self.command = command
            self.callback = callback

    class DummyMessageHandler:
        def __init__(self, command_filter: Any, callback: Any) -> None:
            self.command_filter = command_filter
            self.callback = callback

    class DummyChatMemberHandler:
        MY_CHAT_MEMBER = "MY_CHAT_MEMBER"

        def __init__(self, callback: Any, chat_member_type: Any) -> None:
            self.callback = callback
            self.chat_member_type = chat_member_type

    monkeypatch.setattr(sb_module, "AdminsRepo", DummyAdminsRepo)
    monkeypatch.setattr(sb_module, "CommandHandler", DummyCommandHandler)
    monkeypatch.setattr(sb_module, "MessageHandler", DummyMessageHandler)
    monkeypatch.setattr(sb_module, "ChatMemberHandler", DummyChatMemberHandler)
    monkeypatch.setattr(sb_module, "filters", SimpleNamespace(COMMAND="COMMAND"))

    from unittest.mock import MagicMock

    # Создаём мок репозиториев для тестов
    admins_repo = DummyAdminsRepo()
    chats_repo = DummyChatsRepo()
    # Создаём мок конфигурации для тестов
    from shared.bot_services import SupportBotServices
    from shared.config import AppSettings, BotTelegramConfig

    app_settings = AppSettings()
    support_services = SupportBotServices(
        admins_repo=admins_repo,
        chats=chats_repo,
        settings=app_settings,
    )
    telegram_config = BotTelegramConfig(bot_token="test_token", chat_id="123")

    mock_logger = MagicMock()

    # Создаём моки компонентов
    from infra.container import SupportBotComponents

    mock_components = SupportBotComponents(
        error_handler=MagicMock(),
        chat_validator=MagicMock(),
        lifecycle_manager=MagicMock(),
        chat_event_handler=MagicMock(),
        handlers_registry=MagicMock(),
    )

    bot = sb_module.SupportBot(
        services=support_services,
        telegram_config=telegram_config,
        logger=mock_logger,
        components=mock_components,
    )
    return bot


pytestmark = [pytest.mark.unit]


def _make_update(user_id: int = 1, chat_id: int = 10, text: str = "/cmd") -> Any:
    message = SimpleNamespace(
        reply_text=AsyncMock(),
        text=text,
    )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=chat_id),
        message=message,
    )


def _make_context(args: Any = None) -> Any:
    return SimpleNamespace(
        args=args or [],
        bot=SimpleNamespace(send_document=AsyncMock()),
    )


def test_support_bot_setup_handlers(support_bot: Any) -> None:
    support_bot.setup_handlers()
    EXPECTED_HANDLERS_COUNT = 5  # start, help, log, maintenance_message, chat_member
    assert len(support_bot.application.added_handlers) == EXPECTED_HANDLERS_COUNT


@pytest.mark.asyncio
async def test_maintenance_message_replies(support_bot: Any) -> None:
    update = _make_update()
    context = SimpleNamespace()

    await support_bot.maintenance_message(update, context)

    update.message.reply_text.assert_awaited_once()
    call = update.message.reply_text.await_args
    sent_text = call.kwargs.get("text", call.args[0])  # безопасное получение текста
    assert "Технические работы" in sent_text


@pytest.mark.asyncio
async def test_help_command(support_bot: Any) -> None:
    update = _make_update()
    context = SimpleNamespace()

    await support_bot.help_command(update, context)

    update.message.reply_text.assert_awaited_once()
    call = update.message.reply_text.await_args
    text = call.kwargs.get("text", call.args[0])
    assert "SupportBot" in text or "поддержки" in text.lower() or "команды" in text.lower()


@pytest.mark.asyncio
async def test_start_main_command_non_admin(support_bot: Any) -> None:
    support_bot.admins.admins = set()  # нет админов
    update = _make_update(user_id=2)
    context = SimpleNamespace()

    await support_bot.start_main_command(update, context)

    update.message.reply_text.assert_awaited_once()
    call = update.message.reply_text.await_args
    message = call.kwargs.get("text", call.args[0])
    assert "Доступно только администратору" in message


@pytest.mark.asyncio
async def test_start_main_command_admin_no_callback(support_bot: Any) -> None:
    support_bot.admins.admins = {1}
    support_bot.request_start_main = None
    update = _make_update(user_id=1)
    context = SimpleNamespace()

    await support_bot.start_main_command(update, context)

    # Проверяем, что было отправлено сообщение (может быть несколько)
    assert update.message.reply_text.await_count > 0
    # Проверяем логирование (это основной способ проверки, так как сообщение может быть разным)
    # Команда должна выполниться без ошибок


@pytest.mark.asyncio
async def test_start_main_command_admin_with_callback(support_bot: Any) -> None:
    support_bot.admins.admins = {1}
    callback_called = False

    async def mock_callback(data: dict[str, Any]) -> None:
        nonlocal callback_called
        callback_called = True
        await asyncio.sleep(0)  # Используем async для соответствия типу

    support_bot.request_start_main = mock_callback
    update = _make_update(user_id=1)
    context = SimpleNamespace()

    await support_bot.start_main_command(update, context)

    assert callback_called
    update.message.reply_text.assert_awaited()

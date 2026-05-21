"""Тексты пользовательских команд (/start, /help, заглушки)."""

from aiogram.types import BotCommand

WELCOME = (
    "🐸 Привет! Я Wednesday Frog Bot!\n\n"
    "Я генерирую изображения по расписанию (каждую среду) и по команде /generate\n\n"
    "Доступные команды:\n"
    "/start - Показать это сообщение\n"
    "/help - Справка по командам\n"
    "/generate - Сгенерировать изображение (в рамках индивидуального лимита)\n"
)

HELP = (
    "🐸 Справка по командам Wednesday Frog Bot!\n\n"
    "Доступные команды:\n"
    "/start - Показать это сообщение\n"
    "/help - Справка по командам\n"
    "/generate - Сгенерировать изображение (в рамках индивидуального лимита)\n"
)

UNKNOWN_COMMAND = "❓ Неизвестная команда!\n\nИспользуйте /help для получения списка команд."

WIP = "В разработке..."

SET_MODEL_USAGE = "Использование: /set_model <модель>"

# Bot commands in Telegram client.
BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Приветствие и список команд"),
    BotCommand(command="help", description="Справка по командам"),
    BotCommand(command="generate", description="Сгенерировать изображение"),
    BotCommand(command="set_model", description="Выбрать модель для генерации изображений"),
    BotCommand(command="list_models", description="Список доступных моделей"),
)

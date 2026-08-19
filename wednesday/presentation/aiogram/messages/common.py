"""User-facing command texts (/start, /help, stubs)."""

from aiogram.types import BotCommand

WELCOME = (
    "🐸 Привет! Я Wednesday Frog Bot!\n\n"
    "Я генерирую изображения по расписанию (каждую среду) и по команде /generate\n\n"
    "Доступные команды:\n"
    "/start - Показать это сообщение\n"
    "/help - Справка по командам\n"
    "/me - Ваш профиль (роль, подписка, модель, статус)\n"
    "/generate - Сгенерировать изображение (в рамках индивидуального лимита)\n"
    "/random - Случайное изображение из каталога\n"
    "/set_model - Выбрать модель генерации\n"
    "/list_models - Список доступных моделей\n"
    "/reset - Сбросить просмотренные изображения\n"
    "/schedule help - Показать команды для настройки расписания (только в чате)\n"
)

HELP = (
    "🐸 Справка по командам Wednesday Frog Bot!\n\n"
    "Доступные команды:\n"
    "/start - Показать это сообщение\n"
    "/help - Справка по командам\n"
    "/me - Ваш профиль (роль, подписка, модель, статус)\n"
    "/generate - Сгенерировать изображение (в рамках индивидуального лимита)\n"
    "/random - Случайное изображение из каталога\n"
    "/set_model - Выбрать модель генерации\n"
    "/list_models - Список доступных моделей\n"
    "/reset - Сбросить просмотренные изображения\n"
    "/schedule help - Показать команды для настройки расписания (только в чате)\n"
)

UNKNOWN_COMMAND = "❓ Неизвестная команда!\n\nИспользуйте /help для получения списка команд."

WIP = "В разработке..."


# Bot commands in Telegram client.
BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Приветствие и список команд"),
    BotCommand(command="help", description="Справка по командам"),
    BotCommand(command="me", description="Ваш профиль"),
    BotCommand(command="generate", description="Сгенерировать изображение"),
    BotCommand(command="random", description="Случайное изображение из каталога"),
    BotCommand(command="set_model", description="Выбрать модель для генерации изображений"),
    BotCommand(command="list_models", description="Список доступных моделей"),
    BotCommand(command="reset", description="Сбросить просмотренные изображения"),
)

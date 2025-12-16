"""
Обработчики команд для Telegram бота.

Этот модуль больше не содержит класс CommandHandlers.
Все команды были перенесены в специализированные хендлеры:
- UserHandlers (bot/handlers_user.py) - пользовательские команды
- AdminHandlers (bot/handlers_admin.py) - административные команды
- ModelHandlers (bot/handlers_models.py) - команды управления моделями

Общие утилитарные методы находятся в BaseHandlers (bot/base_handlers.py).
"""

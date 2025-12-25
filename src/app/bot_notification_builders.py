"""Билдеры для уведомлений о жизненном цикле бота."""

from __future__ import annotations


class BotLifecycleNotificationBuilder:
    """Билдер для создания сообщений о жизненном цикле бота.

    Инкапсулирует форматирование сообщений о запуске и остановке бота.
    Соблюдает принцип единственной ответственности (SRP): отвечает только
    за форматирование сообщений, не содержит логики отправки.
    """

    @staticmethod
    def build_startup_message() -> str:
        """Создает сообщение о запуске основного бота.

        Returns:
            Форматированное сообщение о запуске бота.
        """
        return (
            "🚀 Wednesday Frog Bot запущен!\n\n"
            "✅ Бот активен и готов к работе\n"
            "📅 Планировщик: включен (Celery)\n"
            "🎨 Генератор изображений: Kandinsky API\n"
            "📝 Логирование: включено\n\n"
            "🐸 Используйте команду /frog для генерации жабы!"
        )

    @staticmethod
    def build_shutdown_message() -> str:
        """Создает сообщение об остановке основного бота.

        Returns:
            Форматированное сообщение об остановке бота.
        """
        return "🛑 Wednesday Frog Bot остановлен!\n\n📝 Логи сохранены в папке logs/\n👋 До свидания!"

    @staticmethod
    def build_support_startup_message() -> str:
        """Создает сообщение о запуске SupportBot.

        Returns:
            Форматированное сообщение о запуске SupportBot.
        """
        return (
            "🟢 SupportBot запущен и принимает команды.\n"
            "• /help — справка\n"
            "• /log — последний лог\n"
            "• /start — запустить основной бот"
        )

    @staticmethod
    def build_support_shutdown_message() -> str:
        """Создает сообщение об остановке SupportBot.

        Returns:
            Форматированное сообщение об остановке SupportBot.
        """
        return "🛑 SupportBot остановлен.\n\nЕсли это не плановая остановка, проверьте логи и состояние основного бота."

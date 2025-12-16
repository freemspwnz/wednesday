"""Настройки приложения для DI.

Легковесный объект настроек, доступный через BotServices,
вместо прямого чтения из глобального config.
"""

from __future__ import annotations

from dataclasses import dataclass

from utils.config import TIME_FORMAT_LENGTH, Config


@dataclass
class AppSettings:
    """Настройки приложения для передачи через DI.

    Инкапсулирует основные настройки, которые ранее читались напрямую
    из глобального config в хендлерах и других компонентах.
    """

    admin_chat_id: int | None
    chat_id: int | None
    scheduler_send_times: list[str]
    frog_rate_limit_minutes: int = 5
    frog_rate_limit_window_seconds: int = 60
    frog_rate_limit_max_requests: int = 10
    scheduler_tz: str = "Europe/Amsterdam"
    time_format_length: int = 5

    @classmethod
    def from_config(cls, config: Config) -> AppSettings:
        """Создает AppSettings из глобального Config.

        Args:
            config: Экземпляр глобального Config.

        Returns:
            Экземпляр AppSettings с настройками из config.
        """
        # Преобразуем admin_chat_id из str в int, если задан
        admin_chat_id: int | None = None
        admin_chat_id_str = config.admin_chat_id
        if admin_chat_id_str:
            try:
                admin_chat_id = int(admin_chat_id_str)
            except (ValueError, TypeError):
                admin_chat_id = None

        # Преобразуем chat_id из str в int, если задан
        chat_id: int | None = None
        chat_id_str = config.chat_id
        if chat_id_str:
            try:
                chat_id = int(chat_id_str)
            except (ValueError, TypeError):
                chat_id = None

        return cls(
            admin_chat_id=admin_chat_id,
            chat_id=chat_id,
            scheduler_send_times=config.scheduler_send_times,
            frog_rate_limit_minutes=5,  # Значение по умолчанию из bot/handlers.py
            frog_rate_limit_window_seconds=60,  # Значение по умолчанию из bot/handlers.py
            frog_rate_limit_max_requests=10,  # Значение по умолчанию из bot/handlers.py
            scheduler_tz=config.scheduler_tz,
            time_format_length=TIME_FORMAT_LENGTH,
        )

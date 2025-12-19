"""Конфигурация для Kandinsky клиента."""

from __future__ import annotations

from dataclasses import dataclass

from utils.config import Config


@dataclass(frozen=True)
class KandinskyConfig:
    """Конфигурация для Kandinsky клиента.

    Инкапсулирует все параметры, необходимые для инициализации KandinskyClient.
    """

    api_key: str | None
    secret_key: str | None

    @classmethod
    def from_config(cls, config: Config) -> KandinskyConfig:
        """Создает KandinskyConfig из глобального Config.

        Используется только в container.py при сборке зависимостей.

        Args:
            config: Экземпляр глобального Config.

        Returns:
            Экземпляр KandinskyConfig с настройками из config.
        """
        return cls(
            api_key=config.kandinsky_api_key,
            secret_key=config.kandinsky_secret_key,
        )

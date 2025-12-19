"""Конфигурация для GigaChat клиента."""

from __future__ import annotations

from dataclasses import dataclass

from utils.config import Config


@dataclass(frozen=True)
class GigaChatConfig:
    """Конфигурация для GigaChat клиента.

    Инкапсулирует все параметры, необходимые для инициализации GigaChatTextClient.
    """

    auth_url: str
    api_url: str
    authorization_key: str
    scope: str
    model: str
    verify_ssl: bool | str = True

    @classmethod
    def from_config(cls, config: Config) -> GigaChatConfig:
        """Создает GigaChatConfig из глобального Config.

        Используется только в container.py при сборке зависимостей.

        Args:
            config: Экземпляр глобального Config.

        Returns:
            Экземпляр GigaChatConfig с настройками из config.
        """
        return cls(
            auth_url=config.gigachat_auth_url,
            api_url=config.gigachat_api_url,
            authorization_key=config.gigachat_authorization_key,
            scope=config.gigachat_scope,
            model=config.gigachat_model,
            verify_ssl=config.gigachat_verify_ssl,
        )

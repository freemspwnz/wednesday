"""
Инфраструктура HTTP‑клиентов для внешних ML‑сервисов.

Модуль `infrastructure.clients` содержит:

- тонкие обёртки над внешними API (Kandinsky, GigaChat и др.);
- протоколы-интерфейсы для текст‑к‑изображению и текст‑к‑тексту моделей;
- фабрики для выбора конкретных реализаций по переменным окружения.

Ключевая цель — отделить сетевую/HTTP‑логику и детали авторизации
от бизнес‑логики генерации (`ImageGenerator`), чтобы:

- облегчить замену моделей и провайдеров без переписывания бота;
- упростить тестирование через структурные Protocol‑интерфейсы;
- централизовать политику ретраев и обработку сетевых ошибок.
"""

from infra.clients.image_client_container import (
    ImageClientContainer,
    get_image_client_container,
)
from infra.clients.sber_clients_exceptions import should_retry
from infra.clients.text_client_container import (
    TextClientContainer,
    get_text_client_container,
)
from shared.base.exceptions import (
    APIError,
    AuthenticationError,
    ClientError,
    NetworkError,
    RateLimitError,
)
from shared.protocols import ITextToImageClient, ITextToTextClient

__all__ = [
    "APIError",
    "AuthenticationError",
    "ClientError",
    "ITextToImageClient",
    "ITextToTextClient",
    "ImageClientContainer",
    "NetworkError",
    "RateLimitError",
    "TextClientContainer",
    "get_image_client_container",
    "get_text_client_container",
    "should_retry",
]

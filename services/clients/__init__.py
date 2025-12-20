"""
Инфраструктура HTTP‑клиентов для внешних ML‑сервисов.

Модуль `services.clients` содержит:

- тонкие обёртки над внешними API (Kandinsky, GigaChat и др.);
- протоколы-интерфейсы для текст‑к‑изображению и текст‑к‑тексту моделей;
- фабрики для выбора конкретных реализаций по переменным окружения.

Ключевая цель — отделить сетевую/HTTP‑логику и детали авторизации
от бизнес‑логики генерации (`ImageGenerator`), чтобы:

- облегчить замену моделей и провайдеров без переписывания бота;
- упростить тестирование через структурные Protocol‑интерфейсы;
- централизовать политику ретраев и обработку сетевых ошибок.
"""

from services.clients.error_handling import log_client_error, should_retry
from services.clients.exceptions import (
    APIError,
    AuthenticationError,
    ClientError,
    NetworkError,
    RateLimitError,
)
from services.clients.image_client_container import (
    ImageClientContainer,
    get_image_client_container,
)
from services.clients.text_client_container import (
    TextClientContainer,
    get_text_client_container,
)
from services.protocols import ITextToImageClient, ITextToTextClient

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
    "log_client_error",
    "should_retry",
]

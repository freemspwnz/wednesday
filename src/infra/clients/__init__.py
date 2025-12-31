"""
Инфраструктура HTTP‑клиентов для внешних ML‑сервисов.

Модуль `infra.clients` содержит:

- тонкие обёртки над внешними API (Kandinsky, GigaChat и др.);
- протоколы-интерфейсы для текст‑к‑изображению и текст‑к‑тексту моделей;
- контейнеры для runtime-замены клиентов без рестарта;
- ClientManagementService для создания клиентов через DI.

Клиенты создаются через Dependency Injection в `infra.container._create_clients()`
с использованием `ClientManagementService`.

Ключевая цель — отделить сетевую/HTTP‑логику и детали авторизации
от бизнес‑логики генерации (`ImageService`), чтобы:

- облегчить замену моделей и провайдеров без переписывания бота;
- упростить тестирование через структурные Protocol‑интерфейсы;
- централизовать политику ретраев и обработку сетевых ошибок;
- обеспечить runtime-замену клиентов через контейнеры с поддержкой кастомных конфигов.
"""

from infra.clients.client_manager import ClientManagementService
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
from shared.protocols.clients import ITextToImageClient, ITextToTextClient

__all__ = [
    "APIError",
    "AuthenticationError",
    "ClientError",
    "ClientManagementService",
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

"""Пакет с модульной реализацией Composition Root для бота.

Сюда вынесена логика из старого монолитного `infra.container.Container`,
разделённая по зонам ответственности:

- `repos` — репозитории и инфраструктурные компоненты (cached_property);
- `client_builders` — фабрики ML‑клиентов (Kandinsky, GigaChat);
- `domain_builders` — доменные сервисы генерации промптов и изображений;
- `image_stack_builder` — сборка полного стека для `ImageService`;
- `rate_limiter_builders` — фабрики rate‑limiters и circuit breaker;
- `service_builders` — application‑сервисы (админка, БД‑операции, модели);
- `handler_builders` — создание PTB‑хендлеров и реестра.

Публичной точкой входа является класс `Container`, который выступает тонким
координатором и делегирует создание зависимостей в эти модули.
"""

from .container import Container

__all__ = ["Container"]

"""
Исторический модуль с синхронным файловым хранилищем промптов.

После унификации хранилищ промптов:
- вся логика перенесена в асинхронный `PromptStorageService`,
  реализующий протокол `IPromptStorage`;
- этот модуль больше не используется и подлежит удалению.

Для использования хранилища промптов используйте:
- `services.infrastructure.storage.prompt_storage.PromptStorageService`
- `services.protocols.IPromptStorage` (протокол)
"""

from __future__ import annotations

import warnings

# Предупреждение при импорте устаревшего класса
warnings.warn(
    "Модуль services.prompt_generator устарел. "
    "Используйте services.infrastructure.storage.prompt_storage.PromptStorageService "
    "или services.protocols.IPromptStorage",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = []

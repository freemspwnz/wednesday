"""Composition Root: модульный контейнер зависимостей.

Публичный API:
- Container — единственная точка сборки приложения.
"""

from .container import Container
from .observe import ObserveContainer
from .persistence import PersistenceContainer
from .resilience import ResilienceContainer
from .scope import ScopeContainer

__all__ = [
    "Container",
    "ObserveContainer",
    "PersistenceContainer",
    "ResilienceContainer",
    "ScopeContainer",
]

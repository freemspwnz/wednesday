"""Composition root: modular dependency containers.

Public API:
- Container — single application composition root.
"""

from .container import Container
from .network import NetworkContainer
from .observe import ObserveContainer
from .persistence import PersistenceContainer
from .resilience import ResilienceContainer
from .scope import ScopeContainer

__all__ = [
    "Container",
    "NetworkContainer",
    "ObserveContainer",
    "PersistenceContainer",
    "ResilienceContainer",
    "ScopeContainer",
]

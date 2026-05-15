from __future__ import annotations

from typing import Protocol

from .observe import Logger


class RequestScope(Protocol):
    """Протокол для request scope."""

    @property
    def logger(self) -> Logger: ...

    @property
    def registration_uc(self) -> object: ...

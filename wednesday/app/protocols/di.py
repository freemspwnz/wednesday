from __future__ import annotations

from typing import Protocol

from .observe import ILogger


class IRequestScope(Protocol):
    """Протокол для request scope."""

    @property
    def logger(self) -> ILogger: ...

    @property
    def registration_uc(self) -> object: ...

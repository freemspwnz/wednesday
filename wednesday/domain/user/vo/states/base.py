from __future__ import annotations

from abc import ABC, abstractmethod

from ....kernel.vo import AwareDatetime
from ...exceptions import ValidationError


class UserState(ABC):
    @abstractmethod
    def is_banned_at(self, now: AwareDatetime) -> bool: ...

    @abstractmethod
    def ban_until(self, until: AwareDatetime, now: AwareDatetime) -> UserState: ...

    @abstractmethod
    def unban(self) -> UserState: ...

    @abstractmethod
    def effective_at(self, now: AwareDatetime) -> UserState: ...

    @classmethod
    def ensure(cls, state: UserState) -> UserState:
        if not isinstance(state, cls):
            raise ValidationError("state must be a UserState")
        return state

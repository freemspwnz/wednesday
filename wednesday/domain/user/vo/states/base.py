from abc import ABC, abstractmethod
from typing import Self

from ....kernel.vo import AwareDatetime
from ...exceptions import ValidationError


class UserState(ABC):
    @abstractmethod
    def is_banned_at(self, now: AwareDatetime) -> bool: ...

    @abstractmethod
    def ban_until(self, until: AwareDatetime, now: AwareDatetime) -> "UserState": ...

    @abstractmethod
    def unban(self) -> "UserState": ...

    @abstractmethod
    def effective_at(self, now: AwareDatetime) -> "UserState": ...

    @classmethod
    def ensure(cls, state: object) -> Self:
        if not isinstance(state, cls):
            raise ValidationError(f"State must be an instance of {cls.__name__}")
        return state

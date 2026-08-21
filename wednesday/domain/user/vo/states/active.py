from dataclasses import dataclass

from ....kernel.vo import AwareDatetime
from ...exceptions import ValidationError
from .base import UserState


@dataclass(frozen=True)
class ActiveState(UserState):
    @staticmethod
    def is_banned_at(now: AwareDatetime) -> bool:
        return False

    @staticmethod
    def ban_until(until: AwareDatetime, now: AwareDatetime) -> UserState:
        if until <= now:
            raise ValidationError("until must be in the future")
        from .banned import BannedState

        return BannedState(until=until)

    @staticmethod
    def unban() -> UserState:
        return ActiveState()

    def effective_at(self, now: AwareDatetime) -> UserState:
        return self

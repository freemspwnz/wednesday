from dataclasses import dataclass

from ....kernel.vo import AwareDatetime
from ...exceptions import InvalidStateTransitionError, ValidationError
from .base import UserState


@dataclass(frozen=True)
class BannedState(UserState):
    until: AwareDatetime

    def __post_init__(self) -> None:
        if not isinstance(self.until, AwareDatetime):
            raise ValidationError("until must be AwareDatetime")

    def is_banned_at(self, now: AwareDatetime) -> bool:
        return self.until > now

    def ban_until(self, until: AwareDatetime, now: AwareDatetime) -> "BannedState":
        if until <= now:
            raise ValidationError("until must be in the future")
        if until < self.until and self.until > now:
            raise InvalidStateTransitionError("cannot shorten active ban")
        return BannedState(until=until)

    @staticmethod
    def unban() -> UserState:
        from .active import ActiveState

        return ActiveState()

    def refresh(self, now: AwareDatetime) -> UserState:
        if self.until <= now:
            from .active import ActiveState

            return ActiveState()
        return self

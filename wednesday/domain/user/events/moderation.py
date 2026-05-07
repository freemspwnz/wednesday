from dataclasses import dataclass

from ..vo import AwareDatetime, UserRole
from .base import UserEvent


@dataclass(frozen=True)
class UserBanned(UserEvent):
    until: AwareDatetime
    actor: UserRole

    def __post_init__(self) -> None:
        super().__post_init__()

        UserRole.ensure(self.actor)
        AwareDatetime.ensure(self.until)


@dataclass(frozen=True)
class UserUnbanned(UserEvent):
    actor: UserRole

    def __post_init__(self) -> None:
        super().__post_init__()

        UserRole.ensure(self.actor)


@dataclass(frozen=True)
class UserBanExpired(UserEvent):
    def __post_init__(self) -> None:
        super().__post_init__()

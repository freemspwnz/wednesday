from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import ValidationError
from ..vo import AwareDatetime, UserId


@dataclass(frozen=True)
class UserEvent:
    user_id: UserId
    occurred_at: AwareDatetime

    def __post_init__(self) -> None:
        UserId.ensure(self.user_id)
        AwareDatetime.ensure(self.occurred_at)

    @classmethod
    def ensure(cls, event: UserEvent) -> UserEvent:
        if not isinstance(event, UserEvent):
            raise ValidationError("event must be a UserEvent")
        return event

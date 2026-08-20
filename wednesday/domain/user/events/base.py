from dataclasses import dataclass
from typing import Self

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
    def ensure(cls, event: object) -> Self:
        if not isinstance(event, cls):
            raise ValidationError(f"Event must be an instance of {cls.__name__}")
        return event

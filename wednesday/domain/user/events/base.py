from dataclasses import dataclass

from ..exceptions import ValidationError
from ..vo import AwareDatetime, UserTelegramId


@dataclass(frozen=True)
class UserEvent:
    user_id: UserTelegramId
    occurred_at: AwareDatetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserTelegramId):
            raise ValidationError("user_id must be a UserTelegramId")

        if not isinstance(self.occurred_at, AwareDatetime):
            raise ValidationError("occurred_at must be a AwareDatetime")

from dataclasses import dataclass

from ..exceptions import ValidationError


@dataclass(frozen=True)
class UserTelegramId:
    """User's Telegram ID."""

    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValidationError("User's Telegram ID must be positive")

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)

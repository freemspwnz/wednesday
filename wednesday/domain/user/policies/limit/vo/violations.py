from dataclasses import dataclass
from datetime import timedelta

from ....exceptions import ValidationError
from .code import LimitViolationCode


@dataclass(frozen=True)
class DailyLimitViolation:
    daily_limit: int
    used: int

    def __post_init__(self) -> None:
        if not isinstance(self.daily_limit, int):
            raise ValidationError("daily_limit must be an int")

        if not isinstance(self.used, int):
            raise ValidationError("used must be an int")

        if self.daily_limit < 0:
            raise ValidationError("daily_limit must be >= 0")

        if self.used < 0:
            raise ValidationError("used must be >= 0")

    @property
    def code(self) -> LimitViolationCode:
        return LimitViolationCode.DAILY_LIMIT_EXCEEDED


@dataclass(frozen=True)
class CooldownViolation:
    cooldown_minutes: int
    remaining: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.cooldown_minutes, int):
            raise ValidationError("cooldown_minutes must be an int")

        if not isinstance(self.remaining, timedelta):
            raise ValidationError("remaining must be a timedelta")

        if self.cooldown_minutes < 0:
            raise ValidationError("cooldown_minutes must be >= 0")

        if self.remaining.total_seconds() < 0:
            raise ValidationError("remaining must be >= 0")

    @property
    def code(self) -> LimitViolationCode:
        return LimitViolationCode.COOLDOWN


type LimitViolation = DailyLimitViolation | CooldownViolation

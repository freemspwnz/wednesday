from dataclasses import dataclass

from ....exceptions import ValidationError
from ....vo import AwareDatetime


@dataclass(frozen=True)
class UsageStats:
    """VO: Usage statistics for the limit policy."""

    last_usage: AwareDatetime | None
    daily_usage: int

    def __post_init__(self) -> None:
        if self.daily_usage < 0:
            raise ValidationError("daily_usage must be >= 0")

        if self.last_usage is not None:
            if not isinstance(self.last_usage, AwareDatetime):
                raise ValidationError("last_usage must be a AwareDatetime")

    def validate(self, now: AwareDatetime) -> None:
        if self.last_usage is not None and self.last_usage > now:
            raise ValidationError("last_usage must be <= now")

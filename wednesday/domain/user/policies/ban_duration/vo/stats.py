from dataclasses import dataclass

from ....exceptions import ValidationError


@dataclass(frozen=True)
class ViolationStats:
    today: int
    week: int
    total: int

    def __post_init__(self) -> None:
        if not isinstance(self.today, int):
            raise ValidationError("today must be an int")

        if not isinstance(self.week, int):
            raise ValidationError("week must be an int")

        if not isinstance(self.total, int):
            raise ValidationError("total must be an int")

        if self.today < 0:
            raise ValidationError("today must be >= 0")

        if self.week < 0:
            raise ValidationError("week must be >= 0")

        if self.total < 0:
            raise ValidationError("total must be >= 0")

        if self.today > self.week:
            raise ValidationError("today must be <= week")

        if self.week > self.total:
            raise ValidationError("week must be <= total")

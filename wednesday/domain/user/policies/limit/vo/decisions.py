from dataclasses import dataclass

from ....exceptions import ValidationError
from .violations import CooldownViolation, DailyLimitViolation, LimitViolation


@dataclass(frozen=True)
class LimitAllowed:
    pass


@dataclass(frozen=True)
class LimitDenied:
    violation: LimitViolation

    def __post_init__(self) -> None:
        if not isinstance(self.violation, DailyLimitViolation | CooldownViolation):
            raise ValidationError("violation must be a LimitViolation")


type LimitDecision = LimitAllowed | LimitDenied

from dataclasses import dataclass

from ....exceptions import ValidationError
from .violation import ModerationViolation


@dataclass(frozen=True)
class ModerationAllowed:
    pass


@dataclass(frozen=True)
class ModerationDenied:
    violation: ModerationViolation

    def __post_init__(self) -> None:
        if not isinstance(self.violation, ModerationViolation):
            raise ValidationError("violation must be a ModerationViolation")


type ModerationDecision = ModerationAllowed | ModerationDenied

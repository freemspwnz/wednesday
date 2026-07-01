from dataclasses import dataclass

from ....exceptions import ValidationError
from .code import ModerationCode


@dataclass(frozen=True)
class ModerationViolation:
    code: ModerationCode
    meta: dict[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.code, ModerationCode):
            raise ValidationError("code must be a ModerationCode")

        if not all(isinstance(v, str) for v in self.meta.values()):
            raise ValidationError("meta values must be strings")

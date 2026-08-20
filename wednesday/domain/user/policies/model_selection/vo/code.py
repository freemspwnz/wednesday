from enum import StrEnum
from typing import Self

from ....exceptions import ValidationError


class ModelSelectionCode(StrEnum):
    MODEL_NOT_ACTIVE = "model_not_active"
    TIER_TOO_LOW = "tier_too_low"

    @classmethod
    def ensure(cls, code: object) -> Self:
        if not isinstance(code, cls):
            raise ValidationError(f"Code must be an instance of {cls.__name__}")
        return code

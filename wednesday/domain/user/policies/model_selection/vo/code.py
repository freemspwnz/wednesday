from enum import StrEnum
from typing import Self

from ....exceptions import ValidationError


class ModelSelectionCode(StrEnum):
    MODEL_NOT_ACTIVE = "model_not_active"
    TIER_TOO_LOW = "tier_too_low"

    @classmethod
    def ensure(cls, code: Self) -> Self:
        if not isinstance(code, cls):
            raise ValidationError("code must be a ModelSelectionCode")
        return code

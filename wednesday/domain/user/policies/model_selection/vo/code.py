from __future__ import annotations

from enum import StrEnum

from ....exceptions import ValidationError


class ModelSelectionCode(StrEnum):
    MODEL_NOT_ACTIVE = "model_not_active"
    TIER_TOO_LOW = "tier_too_low"

    @classmethod
    def ensure(cls, code: ModelSelectionCode) -> ModelSelectionCode:
        if not isinstance(code, cls):
            raise ValidationError("code must be a ModelSelectionCode")
        return code

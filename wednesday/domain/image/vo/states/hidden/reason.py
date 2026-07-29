from enum import StrEnum
from typing import Self

from ....exceptions import ValidationError


class HiddenReason(StrEnum):
    ADMIN = "admin"
    RATING = "rating"

    @classmethod
    def ensure(cls, reason: object) -> Self:
        if not isinstance(reason, cls):
            raise ValidationError(f"reason must be an instance of {cls.__name__}")
        return reason

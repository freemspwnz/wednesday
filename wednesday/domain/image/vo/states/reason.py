from enum import StrEnum
from typing import Self

from ...exceptions import ValidationError


class HiddenReason(StrEnum):
    ADMIN = "admin"
    VOTES = "votes"

    @classmethod
    def ensure(cls, reason: Self) -> Self:
        if not isinstance(reason, cls):
            raise ValidationError("reason must be a HiddenReason")
        return reason

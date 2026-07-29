from enum import IntEnum
from typing import Self

from ....kernel import ValidationError


class SubscriptionTier(IntEnum):
    FREE = 0
    PREMIUM = 1

    @classmethod
    def ensure(cls, tier: object) -> Self:
        if not isinstance(tier, cls):
            raise ValidationError(f"tier must be a {cls.__name__}")
        return tier

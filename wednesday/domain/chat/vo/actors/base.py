from typing import Self

from ...exceptions import ValidationError


class ManagementActor:
    """Base class for management actors."""

    @classmethod
    def ensure(cls, actor: Self) -> Self:
        if not isinstance(actor, cls):
            raise ValidationError("actor must be a ManagementActor")
        return actor

from typing import Self

from ...exceptions import ValidationError


class ManagementActor:
    """Base class for management actors."""

    @classmethod
    def ensure(cls, actor: object) -> Self:
        if not isinstance(actor, cls):
            raise ValidationError(f"Actor must be an instance of {cls.__name__}")
        return actor

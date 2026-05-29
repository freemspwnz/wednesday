from typing import Self

from ...exceptions import ValidationError


class ImageStatus:
    """Base class for catalog image visibility status."""

    @classmethod
    def ensure(cls, status: Self) -> Self:
        if not isinstance(status, ImageStatus):
            raise ValidationError("status must be an ImageStatus")
        return status

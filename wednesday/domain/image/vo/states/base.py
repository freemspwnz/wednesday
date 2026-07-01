from typing import Self

from ...exceptions import ValidationError


class ImageState:
    """Base class for catalog image visibility state."""

    @classmethod
    def ensure(cls, state: Self) -> Self:
        if not isinstance(state, ImageState):
            raise ValidationError("state must be an ImageState")
        return state

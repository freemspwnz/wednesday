from typing import Self

from ...exceptions import ValidationError


class ImageState:
    """Base class for catalog image visibility state."""

    @classmethod
    def ensure(cls, state: object) -> Self:
        if not isinstance(state, cls):
            raise ValidationError(f"state must be an instance of {cls.__name__}")
        return state

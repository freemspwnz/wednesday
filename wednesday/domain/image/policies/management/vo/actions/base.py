from typing import Self

from .....exceptions import ValidationError


class ManagementAction:
    @classmethod
    def ensure(cls, action: object) -> Self:
        if not isinstance(action, cls):
            raise ValidationError(f"action must be a {cls.__name__}")
        return action

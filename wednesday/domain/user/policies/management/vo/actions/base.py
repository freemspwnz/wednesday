from typing import Self

from .....exceptions import ValidationError


class ManagementAction:
    @classmethod
    def ensure(cls, action: object) -> Self:
        if not isinstance(action, cls):
            raise ValidationError(f"Action must be an instance of {cls.__name__}")
        return action

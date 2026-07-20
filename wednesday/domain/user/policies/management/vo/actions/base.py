from typing import Self

from .....exceptions import ValidationError


class ManagementAction:
    @classmethod
    def ensure(cls, action: Self) -> Self:
        if not isinstance(action, cls):
            raise ValidationError("action must be a ManagementAction")
        return action

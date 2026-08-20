from enum import IntEnum
from typing import Self

from ..exceptions import ValidationError


class UserRole(IntEnum):
    SYSTEM = 3
    OWNER = 2
    ADMIN = 1
    USER = 0

    @classmethod
    def ensure(cls, role: object) -> Self:
        if not isinstance(role, cls):
            raise ValidationError(f"Role must be an instance of {cls.__name__}")
        return role

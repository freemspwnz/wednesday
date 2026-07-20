from enum import IntEnum
from typing import Self

from ..exceptions import ValidationError


class UserRole(IntEnum):
    SYSTEM = 3
    OWNER = 2
    ADMIN = 1
    USER = 0

    @classmethod
    def ensure(cls, role: Self) -> Self:
        if not isinstance(role, UserRole):
            raise ValidationError("role must be a UserRole")
        return role

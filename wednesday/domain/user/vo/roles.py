from __future__ import annotations

from enum import IntEnum

from ..exceptions import ValidationError


class UserRole(IntEnum):
    SYSTEM = 3
    OWNER = 2
    ADMIN = 1
    USER = 0

    @classmethod
    def ensure(cls, role: UserRole) -> UserRole:
        if not isinstance(role, UserRole):
            raise ValidationError("role must be a UserRole")
        return role

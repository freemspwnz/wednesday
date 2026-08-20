from enum import StrEnum
from typing import Self

from ....exceptions import ValidationError


class ChatMemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    RESTRICTED = "restricted"

    @classmethod
    def ensure(cls, role: object) -> Self:
        if not isinstance(role, cls):
            raise ValidationError(f"Role must be an instance of {cls.__name__}")
        return role

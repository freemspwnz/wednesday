from enum import StrEnum
from typing import Self

from ....exceptions import ValidationError


class ChatMemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    RESTRICTED = "restricted"

    @classmethod
    def ensure(cls, role: Self) -> Self:
        if not isinstance(role, cls):
            raise ValidationError("role must be a ChatMemberRole")
        return role

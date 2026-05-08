from __future__ import annotations

from enum import StrEnum

from ....exceptions import ValidationError


class ChatMemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    RESTRICTED = "restricted"

    @classmethod
    def ensure(cls, role: ChatMemberRole) -> ChatMemberRole:
        if not isinstance(role, cls):
            raise ValidationError("role must be a ChatMemberRole")
        return role

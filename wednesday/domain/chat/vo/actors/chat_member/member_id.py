from __future__ import annotations

from dataclasses import dataclass

from ....exceptions import ValidationError


@dataclass(frozen=True)
class ChatMemberId:
    """ChatMember's ID."""

    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValidationError("ChatMember ID must be positive")

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)

    @classmethod
    def ensure(cls, member_id: ChatMemberId) -> ChatMemberId:
        if not isinstance(member_id, cls):
            raise ValidationError("member_id must be a ChatMemberId")
        return member_id

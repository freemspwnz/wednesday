from dataclasses import dataclass
from typing import Self

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
    def ensure(cls, member_id: object) -> Self:
        if not isinstance(member_id, cls):
            raise ValidationError(f"Member ID must be an instance of {cls.__name__}")
        return member_id

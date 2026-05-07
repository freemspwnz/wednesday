from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from ..exceptions import ValidationError


@dataclass(frozen=True)
class UserId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise ValidationError("value must be UUID")

    def __str__(self) -> str:
        return str(self.value)

    @classmethod
    def new(cls) -> UserId:
        return cls(value=uuid4())

    @classmethod
    def ensure(cls, user_id: UserId) -> UserId:
        if not isinstance(user_id, UserId):
            raise ValidationError("user_id must be a UserId")
        return user_id

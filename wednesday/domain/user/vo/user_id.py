from dataclasses import dataclass
from typing import Self
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

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
    def new(cls) -> Self:
        return cls(value=uuid4())

    @classmethod
    def from_int(cls, other: int) -> Self:
        return cls(value=uuid5(NAMESPACE_DNS, f"user:{other}"))

    @classmethod
    def ensure(cls, user_id: object) -> Self:
        if not isinstance(user_id, cls):
            raise ValidationError(f"user_id must be an instance of {cls.__name__}")
        return user_id

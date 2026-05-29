from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .exceptions import ValidationError
from .vo import ImageId

_VOTE_VALUES = frozenset({-1, 1})


@dataclass(frozen=True)
class Vote:
    image_id: ImageId
    voter_id: UUID
    value: int

    def __post_init__(self) -> None:
        ImageId.ensure(self.image_id)
        if not isinstance(self.voter_id, UUID):
            raise ValidationError("voter_id must be a UUID")
        if self.value not in _VOTE_VALUES:
            raise ValidationError("vote value must be -1 or 1")

    def change(self, new_value: int) -> Vote:
        if new_value not in _VOTE_VALUES:
            raise ValidationError("vote value must be -1 or 1")
        return Vote(
            image_id=self.image_id,
            voter_id=self.voter_id,
            value=new_value,
        )

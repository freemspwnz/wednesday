from dataclasses import dataclass, replace
from typing import Self

from domain.user import UserId

from .exceptions import ValidationError
from .policies import ImageRatingPolicy
from .vo import ImageId


@dataclass(frozen=True)
class Vote:
    image_id: ImageId
    voter_id: UserId
    value: int

    def __post_init__(self) -> None:
        ImageId.ensure(self.image_id)
        UserId.ensure(self.voter_id)
        if self.value not in ImageRatingPolicy.VOTE_VALUES:
            raise ValidationError(f"vote value must be one of {ImageRatingPolicy.VOTE_VALUES}")

    def change(self, value: int) -> Self:
        return replace(self, value=value)

    @classmethod
    def ensure(cls, vote: object) -> Self:
        if not isinstance(vote, cls):
            raise ValidationError(f"vote must be a {cls.__name__}")
        return vote

from dataclasses import dataclass
from typing import Self

from ..exceptions import ValidationError


@dataclass(frozen=True)
class ImageRating:
    likes: int
    dislikes: int

    def __post_init__(self) -> None:
        if not isinstance(self.likes, int) or self.likes < 0:
            raise ValidationError("likes must be a non-negative int")
        if not isinstance(self.dislikes, int) or self.dislikes < 0:
            raise ValidationError("dislikes must be a non-negative int")

    @classmethod
    def ensure(cls, rating: object) -> Self:
        if not isinstance(rating, cls):
            raise ValidationError(f"rating must be an instance of {cls.__name__}")
        return rating

    @property
    def value(self) -> int:
        return self.likes - self.dislikes

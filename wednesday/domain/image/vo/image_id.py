from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4

from ..exceptions import ValidationError


@dataclass(frozen=True)
class ImageId:
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
    def ensure(cls, image_id: Self) -> Self:
        if not isinstance(image_id, ImageId):
            raise ValidationError("image_id must be an ImageId")
        return image_id

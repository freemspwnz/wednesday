from dataclasses import dataclass
from typing import Self
from uuid import UUID

from uuid_utils.compat import uuid7

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
        return cls(value=uuid7())

    @classmethod
    def ensure(cls, image_id: object) -> Self:
        if not isinstance(image_id, cls):
            raise ValidationError(f"image_id must be an instance of {cls.__name__}")
        return image_id

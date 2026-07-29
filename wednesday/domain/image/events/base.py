from dataclasses import dataclass
from typing import Self

from ..exceptions import ValidationError
from ..vo import AwareDatetime, ImageId


@dataclass(frozen=True)
class ImageEvent:
    image_id: ImageId
    occurred_at: AwareDatetime

    def __post_init__(self) -> None:
        ImageId.ensure(self.image_id)
        AwareDatetime.ensure(self.occurred_at)

    @classmethod
    def ensure(cls, event: object) -> Self:
        if not isinstance(event, cls):
            raise ValidationError(f"event must be a {cls.__name__}")
        return event

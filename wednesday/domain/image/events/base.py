from __future__ import annotations

from dataclasses import dataclass

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
    def ensure(cls, event: ImageEvent) -> ImageEvent:
        if not isinstance(event, ImageEvent):
            raise ValidationError("event must be a ImageEvent")
        return event

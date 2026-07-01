from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import ValidationError
from ..vo import ImageMeta, ImagePrompts
from .base import ImageEvent


@dataclass(frozen=True)
class ImageRegistered(ImageEvent):
    meta: ImageMeta
    prompts: ImagePrompts

    def __post_init__(self) -> None:
        super().__post_init__()
        ImageMeta.ensure(self.meta)
        ImagePrompts.ensure(self.prompts)


@dataclass(frozen=True)
class ImageScoreRecalculated(ImageEvent):
    old_score: int
    new_score: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.old_score, int):
            raise ValidationError("old_score must be an int")
        if not isinstance(self.new_score, int):
            raise ValidationError("new_score must be an int")

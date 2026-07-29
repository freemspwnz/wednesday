from dataclasses import dataclass

from ..vo import ImageMeta, ImagePrompts, ImageRating
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
class ImageRatingChanged(ImageEvent):
    old: ImageRating
    new: ImageRating

    def __post_init__(self) -> None:
        super().__post_init__()
        ImageRating.ensure(self.old)
        ImageRating.ensure(self.new)

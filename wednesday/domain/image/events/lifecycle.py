from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import ValidationError
from ..vo import ImageMeta, ImagePrompts, TelegramFileId
from .base import ImageEvent


@dataclass(frozen=True)
class ImageRegistered(ImageEvent):
    meta: ImageMeta
    prompts: ImagePrompts | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        ImageMeta.ensure(self.meta)
        if self.prompts is not None:
            ImagePrompts.ensure(self.prompts)


@dataclass(frozen=True)
class ImageFileAttached(ImageEvent):
    file_id: TelegramFileId

    def __post_init__(self) -> None:
        super().__post_init__()
        TelegramFileId.ensure(self.file_id)


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


@dataclass(frozen=True)
class ImageAdminHidden(ImageEvent):
    def __post_init__(self) -> None:
        super().__post_init__()


@dataclass(frozen=True)
class ImageAdminRestored(ImageEvent):
    def __post_init__(self) -> None:
        super().__post_init__()

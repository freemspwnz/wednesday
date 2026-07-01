from dataclasses import dataclass
from typing import Self

from ..exceptions import ValidationError
from .prompts import ImagePrompts


@dataclass(frozen=True)
class ImageRender:
    """Output of the image generation pipeline before catalog registration."""

    content: bytes
    prompts: ImagePrompts

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise ValidationError("content must be bytes")
        if not self.content:
            raise ValidationError("content cannot be empty")
        ImagePrompts.ensure(self.prompts)

    @classmethod
    def ensure(cls, render: Self) -> Self:
        if not isinstance(render, ImageRender):
            raise ValidationError("render must be an ImageRender")
        return render

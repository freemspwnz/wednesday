from dataclasses import dataclass
from typing import Self

from ...exceptions import ValidationError
from .normalized import NormalizedPrompt
from .source import PromptSource


@dataclass(frozen=True)
class ImagePrompts:
    primary: NormalizedPrompt
    source: PromptSource
    enriched: NormalizedPrompt | None = None

    def __post_init__(self) -> None:
        NormalizedPrompt.ensure(self.primary)
        PromptSource.ensure(self.source)
        if self.source != PromptSource.USER and self.enriched is not None:
            raise ValidationError("enriched prompt is not allowed for non-user sources")
        if self.enriched is not None:
            NormalizedPrompt.ensure(self.enriched)

    @classmethod
    def ensure(cls, prompts: Self) -> Self:
        if not isinstance(prompts, ImagePrompts):
            raise ValidationError("prompts must be an ImagePrompts")
        return prompts

    def effective(self) -> NormalizedPrompt:
        return self.enriched or self.primary

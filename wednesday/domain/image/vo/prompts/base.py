from dataclasses import dataclass
from typing import Self

from ...exceptions import ValidationError
from .normalized_prompt import NormalizedPrompt


@dataclass(frozen=True)
class ImagePrompts:
    user: NormalizedPrompt | None = None
    enriched: NormalizedPrompt | None = None

    def __post_init__(self) -> None:
        if self.user is not None:
            NormalizedPrompt.ensure(self.user)
        if self.enriched is not None:
            NormalizedPrompt.ensure(self.enriched)

    @classmethod
    def create(
        cls,
        *,
        user: NormalizedPrompt | None = None,
        enriched: NormalizedPrompt | None = None,
    ) -> Self:
        return cls(user=user, enriched=enriched)

    @classmethod
    def parse(
        cls,
        *,
        user: str | None = None,
        enriched: str | None = None,
    ) -> Self:
        return cls(
            user=NormalizedPrompt.parse(user) if user else None,
            enriched=NormalizedPrompt.parse(enriched) if enriched else None,
        )

    @classmethod
    def ensure(cls, prompts: Self) -> Self:
        if not isinstance(prompts, ImagePrompts):
            raise ValidationError("prompts must be an ImagePrompts")
        return prompts

from dataclasses import dataclass
from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError


@dataclass(frozen=True)
class PromptComponents:
    """Snapshot of prompt building blocks for fallback generation."""

    heroes: tuple[str, ...]
    colors: tuple[str, ...]
    styles: tuple[str, ...]
    professions: tuple[str, ...]
    actions: tuple[str, ...]
    places: tuple[str, ...]
    portraits: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, items in (
            ("heroes", self.heroes),
            ("colors", self.colors),
            ("styles", self.styles),
            ("professions", self.professions),
            ("actions", self.actions),
            ("places", self.places),
            ("portraits", self.portraits),
        ):
            if not isinstance(items, tuple) or not items:
                raise ValidationError(f"{name} must be a non-empty tuple")
            if not all(isinstance(item, str) and item.strip() for item in items):
                raise ValidationError(f"{name} must contain non-empty strings")


@runtime_checkable
class PromptCatalog(Protocol):
    """Read-only registry of system prompts and prompt components."""

    async def enrichment_prompt(self) -> str:
        """System prompt for user input enrichment."""
        ...

    async def generation_prompt(self) -> str:
        """System prompt for image generation."""
        ...

    async def base_prompt(self) -> str:
        """System prompt for random prompt generation."""
        ...

    async def components(self) -> PromptComponents:
        """Building blocks for fallback prompt assembly."""
        ...

    @classmethod
    def ensure(cls, catalog: Self) -> Self:
        if not isinstance(catalog, cls):
            raise ValidationError("catalog must be a PromptCatalog")
        return catalog

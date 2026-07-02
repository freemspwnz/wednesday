from dataclasses import dataclass

from domain.image.protocols import PromptCatalog, PromptComponents


@dataclass(slots=True)
class YamlPromptCatalog(PromptCatalog):
    """Read-only in-memory PromptCatalog snapshot."""

    _enrichment_prompt: str
    _generation_prompt: str
    _base_prompt: str
    _components: PromptComponents

    async def enrichment_prompt(self) -> str:
        return self._enrichment_prompt

    async def generation_prompt(self) -> str:
        return self._generation_prompt

    async def base_prompt(self) -> str:
        return self._base_prompt

    async def components(self) -> PromptComponents:
        return self._components

import random

from ..protocols import PromptCatalog
from ..vo import NormalizedPrompt


class FallbackPromptService:
    """Build fallback prompts when the LLM is unavailable or returns an error."""

    @classmethod
    async def build(cls, catalog: PromptCatalog) -> NormalizedPrompt:
        catalog = PromptCatalog.ensure(catalog)
        components = await catalog.components()

        hero = random.choice(components.heroes)
        color = random.choice(components.colors)
        style = random.choice(components.styles)
        profession = random.choice(components.professions)
        action = random.choice(components.actions)
        place = random.choice(components.places)
        portrait = random.choice(components.portraits)

        prompt = f"Wednesday meme frog, {hero}, {color}, {style}, {profession}, {action}, {place}, {portrait}"
        return NormalizedPrompt.parse(prompt)

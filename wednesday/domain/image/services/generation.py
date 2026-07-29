from random import choice

from domain.catalog import Model

from ..exceptions import GenerationError, ValidationError
from ..image import Image
from ..policies import PromptModerationPolicy
from ..protocols import Generator, PromptCatalog
from ..vo import ImagePrompts, ImageRender, NormalizedPrompt, PromptSource


class ImageGenerationService:
    """Orchestrate prompt preparation and image rendering.

    Callers that charge user quota should moderate first (Image.moderate /
    by_user raises PromptRejectedError) before UserGenerationService.record_usage,
    so a rejected prompt does not consume a generation slot.
    """

    @staticmethod
    async def by_user(
        *,
        model: Model,
        prompt: NormalizedPrompt,
        catalog: PromptCatalog,
        policy: PromptModerationPolicy,
        gen: Generator,
    ) -> ImageRender:
        model = Model.ensure(model)
        prompt = NormalizedPrompt.ensure(prompt)
        catalog = PromptCatalog.ensure(catalog)
        gen = Generator.ensure(gen)

        Image.moderate(prompt=prompt, policy=policy)

        enriched: NormalizedPrompt | None = None
        enrichment_system = await catalog.enrichment_prompt()
        try:
            enriched_raw = await gen.generate_text(
                model=str(model),
                system_prompt=enrichment_system,
                user_prompt=str(prompt),
            )
            enriched = NormalizedPrompt.parse(enriched_raw)
        except (GenerationError, ValidationError):
            pass

        prompts = ImagePrompts(
            primary=prompt,
            source=PromptSource.USER,
            enriched=enriched,
        )

        generation_system = await catalog.generation_prompt()

        content = await gen.generate_image(
            model=str(model),
            system_prompt=generation_system,
            user_prompt=str(prompts.effective()),
        )

        return ImageRender(content=content, prompts=prompts)

    @staticmethod
    async def random(
        *,
        model: Model,
        catalog: PromptCatalog,
        gen: Generator,
    ) -> ImageRender:
        model = Model.ensure(model)
        catalog = PromptCatalog.ensure(catalog)
        gen = Generator.ensure(gen)

        source = PromptSource.LLM
        base_system = await catalog.base_prompt()

        try:
            prompt = NormalizedPrompt.parse(
                await gen.generate_text(
                    model=str(model),
                    system_prompt=base_system,
                    user_prompt="",
                ),
            )
        except (GenerationError, ValidationError):
            prompt = await ImageGenerationService.fallback_prompt(catalog=catalog)
            source = PromptSource.FALLBACK

        prompts = ImagePrompts(primary=prompt, source=source)
        generation_system = await catalog.generation_prompt()

        content = await gen.generate_image(
            model=str(model),
            system_prompt=generation_system,
            user_prompt=str(prompts.effective()),
        )

        return ImageRender(content=content, prompts=prompts)

    @staticmethod
    async def fallback_prompt(*, catalog: PromptCatalog) -> NormalizedPrompt:
        catalog = PromptCatalog.ensure(catalog)
        components = await catalog.components()

        hero = choice(components.heroes)
        color = choice(components.colors)
        style = choice(components.styles)
        profession = choice(components.professions)
        action = choice(components.actions)
        place = choice(components.places)
        portrait = choice(components.portraits)

        prompt = f"Wednesday meme frog, {hero}, {color}, {style}, {profession}, {action}, {place}, {portrait}"
        return NormalizedPrompt.parse(prompt)

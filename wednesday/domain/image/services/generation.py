from __future__ import annotations

from domain.catalog import Model

from ..exceptions import TextGenError, ValidationError
from ..image import Image
from ..policies import PromptModerationPolicy
from ..protocols import ImageGenerator, PromptCatalog, TextGenerator
from ..vo import ImagePrompts, ImageRender, NormalizedPrompt, PromptSource
from .fallback import FallbackPromptService


class ImageGenerationService:
    """Orchestrate prompt preparation and image rendering."""

    @classmethod
    async def by_user(  # noqa: PLR0913
        cls,
        *,
        model: Model,
        user_input: NormalizedPrompt,
        catalog: PromptCatalog,
        moderation: PromptModerationPolicy,
        txt_gen: TextGenerator,
        img_gen: ImageGenerator,
    ) -> ImageRender:
        model = Model.ensure(model)
        user_input = NormalizedPrompt.ensure(user_input)
        catalog = PromptCatalog.ensure(catalog)
        txt_gen = TextGenerator.ensure(txt_gen)
        img_gen = ImageGenerator.ensure(img_gen)

        Image.moderate(user_input=user_input, moderation=moderation)

        enriched: NormalizedPrompt | None = None
        enrichment_system = await catalog.enrichment_prompt()
        try:
            enriched_raw = await txt_gen.generate(
                model=str(model),
                user_prompt=str(user_input),
                system_prompt=enrichment_system,
            )
            enriched = NormalizedPrompt.parse(enriched_raw)
        except (TextGenError, ValidationError):
            pass

        prompts = ImagePrompts(
            primary=user_input,
            source=PromptSource.USER,
            enriched=enriched,
        )

        generation_system = await catalog.generation_prompt()

        content = await img_gen.generate(
            model=str(model),
            system_prompt=generation_system,
            user_prompt=str(prompts.effective()),
        )

        return ImageRender(content=content, prompts=prompts)

    @classmethod
    async def random(
        cls,
        *,
        model: Model,
        catalog: PromptCatalog,
        txt_gen: TextGenerator,
        img_gen: ImageGenerator,
    ) -> ImageRender:
        catalog = PromptCatalog.ensure(catalog)
        model = Model.ensure(model)
        txt_gen = TextGenerator.ensure(txt_gen)
        img_gen = ImageGenerator.ensure(img_gen)

        source = PromptSource.LLM
        base_system = await catalog.base_prompt()

        try:
            prompt = NormalizedPrompt.parse(
                await txt_gen.generate(
                    model=str(model),
                    user_prompt="",
                    system_prompt=base_system,
                )
            )
        except (TextGenError, ValidationError):
            prompt = await FallbackPromptService.build(catalog)
            source = PromptSource.FALLBACK

        prompts = ImagePrompts(primary=prompt, source=source)
        generation_system = await catalog.generation_prompt()

        content = await img_gen.generate(
            model=str(model),
            system_prompt=generation_system,
            user_prompt=str(prompts.effective()),
        )

        return ImageRender(content=content, prompts=prompts)

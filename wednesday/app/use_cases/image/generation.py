from random import choice

from app.dto import ImageCard
from app.protocols import GeneratorRegistry, Logger, UoW
from domain.catalog import Model, Vendor
from domain.chat import ChatId
from domain.image import (
    GenerationError,
    Image,
    ImageId,
    ImageMeta,
    ImagePrompts,
    ImageRender,
    NormalizedPrompt,
    PromptCatalog,
    PromptModerationPolicy,
    PromptSource,
    TelegramFileId,
    ValidationError,
)
from domain.kernel import AwareDatetime

from .base import ImageBaseUseCase


class ImageGenerationUseCase(ImageBaseUseCase):
    """Image render + post-send catalog registration.

    Register uses a short transaction after Telegram provides file_id;
    HTTP render methods stay outside UoW.
    """

    def __init__(
        self,
        *,
        generators: GeneratorRegistry,
        prompts: PromptCatalog,
        policy: PromptModerationPolicy,
        uow: UoW,
        logger: Logger,
    ) -> None:
        super().__init__(uow=uow, logger=logger)
        self._generators = generators
        self._prompts = prompts
        self._policy = policy

    async def by_user(
        self,
        *,
        vendor: Vendor,
        model: Model,
        prompt: str,
    ) -> ImageRender:
        self._logger.debug(
            "Image generation by user started",
            model=str(model),
        )
        gen = self._generators.resolve(vendor)
        resolved_model = Model.ensure(model)
        normalized = NormalizedPrompt.parse(prompt)
        Image.moderate(prompt=normalized, policy=self._policy)

        enriched: NormalizedPrompt | None = None
        enrichment_system = await self._prompts.enrichment_prompt()
        try:
            enriched_raw = await gen.generate_text(
                model=str(resolved_model),
                system_prompt=enrichment_system,
                user_prompt=str(normalized),
            )
            enriched = NormalizedPrompt.parse(enriched_raw)
        except (GenerationError, ValidationError):
            pass

        prompts = ImagePrompts(
            primary=normalized,
            source=PromptSource.USER,
            enriched=enriched,
        )
        generation_system = await self._prompts.generation_prompt()
        content = await gen.generate_image(
            model=str(resolved_model),
            system_prompt=generation_system,
            user_prompt=str(prompts.effective()),
        )
        render = ImageRender(content=content, prompts=prompts)
        self._logger.info(
            "Image generation by user finished",
            model=str(model),
            bytes=len(render.content),
        )
        return render

    async def random(self, *, vendor: Vendor, model: Model) -> ImageRender:
        self._logger.debug("Random image generation started", model=str(model))
        gen = self._generators.resolve(vendor)
        resolved_model = Model.ensure(model)
        source = PromptSource.LLM
        base_system = await self._prompts.base_prompt()
        try:
            prompt = NormalizedPrompt.parse(
                await gen.generate_text(
                    model=str(resolved_model),
                    system_prompt=base_system,
                    user_prompt="",
                ),
            )
        except (GenerationError, ValidationError):
            prompt = await self._fallback_prompt()
            source = PromptSource.FALLBACK

        prompts = ImagePrompts(primary=prompt, source=source)
        generation_system = await self._prompts.generation_prompt()
        content = await gen.generate_image(
            model=str(resolved_model),
            system_prompt=generation_system,
            user_prompt=str(prompts.effective()),
        )
        render = ImageRender(content=content, prompts=prompts)
        self._logger.info(
            "Random image generation finished",
            model=str(model),
            bytes=len(render.content),
        )
        return render

    async def register(  # noqa: PLR0913
        self,
        *,
        image_id: ImageId,
        file_id: TelegramFileId,
        meta: ImageMeta,
        render: ImageRender,
        chat_id: ChatId,
        at: AwareDatetime,
    ) -> ImageCard:
        """Persist a catalog image after Telegram upload yields file_id.

        Records a view for the chat that already received the photo so
        /random will not pick it again in the same chat.
        """

        image = Image.register(
            id=image_id,
            meta=meta,
            file_id=file_id,
            prompts=render.prompts,
            created_at=at,
        )
        self._logger.debug(
            "Image catalog registration started",
            image_id=str(image.id.value),
            author_id=str(meta.author_id.value),
            chat_id=str(chat_id.value),
        )
        async with self._uow:
            await self._uow.images.save(image)
            await self._uow.views.mark_shown(chat_id, image.id, at=at)
        self._logger.info(
            "Image aggregate registered",
            image_id=str(image.id.value),
            author_id=str(meta.author_id.value),
            chat_id=str(chat_id.value),
        )
        return ImageCard.from_domain(image)

    async def _fallback_prompt(self) -> NormalizedPrompt:
        components = await self._prompts.components()
        hero = choice(components.heroes)
        color = choice(components.colors)
        style = choice(components.styles)
        profession = choice(components.professions)
        action = choice(components.actions)
        place = choice(components.places)
        portrait = choice(components.portraits)
        prompt = f"Wednesday meme frog, {hero}, {color}, {style}, {profession}, {action}, {place}, {portrait}"
        return NormalizedPrompt.parse(prompt)

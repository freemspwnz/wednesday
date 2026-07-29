from app.dto import ImageCard
from app.protocols import Logger, UoW
from domain.catalog import Model
from domain.image import (
    Generator,
    Image,
    ImageGenerationService,
    ImageId,
    ImageMeta,
    ImageRender,
    NormalizedPrompt,
    PromptCatalog,
    PromptModerationPolicy,
    TelegramFileId,
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
        gen: Generator,
        prompts: PromptCatalog,
        policy: PromptModerationPolicy,
        uow: UoW,
        logger: Logger,
    ) -> None:
        super().__init__(uow=uow, logger=logger)
        self._gen = gen
        self._prompts = prompts
        self._policy = policy

    async def by_user(
        self,
        *,
        model: Model,
        prompt: str,
    ) -> ImageRender:
        self._logger.debug(
            "Image generation by user started",
            model=str(model),
        )
        normalized = NormalizedPrompt.parse(prompt)
        render = await ImageGenerationService.by_user(
            model=model,
            prompt=normalized,
            catalog=self._prompts,
            policy=self._policy,
            gen=self._gen,
        )
        self._logger.debug(
            "Image generation by user finished",
            model=str(model),
            bytes=len(render.content),
        )
        return render

    async def random(self, *, model: Model) -> ImageRender:
        self._logger.debug("Random image generation started", model=str(model))
        render = await ImageGenerationService.random(
            model=model,
            catalog=self._prompts,
            gen=self._gen,
        )
        self._logger.debug(
            "Random image generation finished",
            model=str(model),
            bytes=len(render.content),
        )
        return render

    async def register(
        self,
        *,
        image_id: ImageId,
        file_id: TelegramFileId,
        meta: ImageMeta,
        render: ImageRender,
        at: AwareDatetime,
    ) -> ImageCard:
        """Persist a catalog image after Telegram upload yields file_id."""

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
        )
        async with self._uow:
            await self._uow.images.save(image)
        self._logger.info(
            "Image aggregate registered",
            image_id=str(image.id.value),
            author_id=str(meta.author_id.value),
        )
        return ImageCard.from_domain(image)

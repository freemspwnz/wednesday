from uuid import UUID

from app.dto import ImageCard
from app.protocols import Logger, UoW
from domain.catalog import Model
from domain.image import (
    Image,
    ImageGenerationService,
    ImageGenerator,
    ImageId,
    ImageMeta,
    ImageRender,
    NormalizedPrompt,
    PromptCatalog,
    PromptModerationPolicy,
    TelegramFileId,
    TextGenerator,
)
from domain.kernel.vo import AwareDatetime

from .base import ImageBaseUseCase


class ImageGenerationUseCase(ImageBaseUseCase):
    """Image render + post-send catalog registration.

    Register uses a short transaction after Telegram provides file_id;
    HTTP render methods stay outside UoW.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        uow: UoW,
        prompts: PromptCatalog,
        txt_gen: TextGenerator,
        img_gen: ImageGenerator,
        moderation: PromptModerationPolicy,
        logger: Logger,
    ) -> None:
        super().__init__(uow=uow, logger=logger)
        self._prompts = prompts
        self._txt_gen = txt_gen
        self._img_gen = img_gen
        self._moderation = moderation

    async def by_user(
        self,
        *,
        model: Model,
        user_input: NormalizedPrompt,
    ) -> ImageRender:
        self._logger.debug(
            "Image generation by user started",
            model=str(model),
        )
        render = await ImageGenerationService.by_user(
            model=model,
            user_input=user_input,
            catalog=self._prompts,
            moderation=self._moderation,
            txt_gen=self._txt_gen,
            img_gen=self._img_gen,
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
            txt_gen=self._txt_gen,
            img_gen=self._img_gen,
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
        render: ImageRender,
        file_id: TelegramFileId,
        author_id: UUID,
        model: Model,
        at: AwareDatetime,
    ) -> ImageCard:
        """Persist a catalog image after Telegram upload yields file_id."""

        image = Image.register(
            id=ImageId.new(),
            meta=ImageMeta(author_id=author_id, model=model),
            file_id=file_id,
            prompts=render.prompts,
            created_at=at,
        )
        self._logger.debug(
            "Image catalog registration started",
            image_id=str(image.id.value),
            author_id=str(author_id),
        )
        async with self._uow:
            await self._uow.images.save(image)
        self._logger.info(
            "Image aggregate registered",
            image_id=str(image.id.value),
            author_id=str(author_id),
        )
        return ImageCard.from_domain(image)

"""Image catalog and generation router."""

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from app.dto import ChatContext, UserContext
from app.protocols import RequestScope
from domain.catalog import Model
from domain.image import ImageId, ImageMeta, PromptRejectedError, TelegramFileId
from domain.kernel.vo import AwareDatetime

from ...messages import image as image_msg
from ...messages.exceptions import user_message_for_exception
from ..utils import run_message_handler
from .vote import build_vote_kb, vote_router

image_router = Router(name="image")
image_router.include_router(vote_router)


@image_router.message(Command("random"))
async def cmd_random(
    message: Message,
    chat: ChatContext,
    scope: RequestScope,
) -> None:
    """Send a random unseen catalog image for the current chat."""

    async def _action() -> None:
        card = await scope.image_catalog_uc.pick_for_chat(
            chat_id=chat.id,
            at=AwareDatetime.now_utc(),
        )
        if card is None:
            await message.answer(image_msg.RANDOM_CATALOG_EMPTY)
            return

        await message.answer_photo(
            photo=str(card.file_id),
            reply_markup=build_vote_kb(image_id=str(card.id), rating=card.rating),
        )

    await run_message_handler(message, scope.logger, _action)


@image_router.message(Command("generate"))
async def cmd_generate(
    message: Message,
    command: CommandObject,
    user: UserContext,
    scope: RequestScope,
) -> None:
    """Generate an image from a user prompt or a random LLM prompt."""

    async def _action() -> None:
        logger = scope.logger.bind(module="image_router")
        at = AwareDatetime.now_utc()
        model = Model.parse(user.model)
        raw_prompt = (command.args or "").strip()

        await scope.user_generation_uc.assert_allowed(user_id=user.id, at=at)
        status = await message.answer(image_msg.GENERATION_STARTED)

        if raw_prompt:
            try:
                render = await scope.image_generation_uc.by_user(model=model, prompt=raw_prompt)
            except PromptRejectedError as exc:
                await scope.user_moderation_uc.assign_ban(user_id=user.id, at=at)
                await status.edit_text(user_message_for_exception(exc))
                return
        else:
            render = await scope.image_generation_uc.random(model=model)

        sent = await message.answer_photo(
            photo=BufferedInputFile(render.content, filename="wednesday.png"),
        )
        if not sent.photo:
            logger.error("Telegram returned photo message without photo sizes")
            return

        file_id = TelegramFileId.parse(sent.photo[-1].file_id)
        image_id = ImageId.new()
        card = await scope.image_generation_uc.register(
            image_id=image_id,
            file_id=file_id,
            meta=ImageMeta(author_id=user.id, model=model),
            render=render,
            at=at,
        )
        await sent.edit_reply_markup(
            reply_markup=build_vote_kb(image_id=str(card.id), rating=card.rating),
        )
        await scope.user_generation_uc.record_usage(user_id=user.id, at=at)

        try:
            await status.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            logger.debug("Failed to delete generate status message", exc_info=True)

    await run_message_handler(message, scope.logger, _action)

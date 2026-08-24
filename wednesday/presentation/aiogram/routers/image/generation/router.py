"""Image generation router."""

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from app.dto import ChatContext, UserContext
from app.protocols import RequestScope
from domain.image import PromptRejectedError
from presentation.aiogram.errors.messages import user_message_for_exception

from ...utils import run_message_handler
from ..vote import build_vote_kb
from . import messages as generation_msg

generation_router = Router(name="generation")


@generation_router.message(Command("random"))
async def cmd_random(
    message: Message,
    chat: ChatContext,
    scope: RequestScope,
) -> None:
    """Send a random unseen catalog image for the current chat."""

    async def _action() -> None:
        at = message.date
        card = await scope.image_catalog_uc.pick_for_chat(chat_id=chat.id)

        if card is None:
            await message.answer(generation_msg.RANDOM_CATALOG_EMPTY)
            return

        await message.answer_photo(
            photo=card.file_id,
            reply_markup=build_vote_kb(image_id=card.id, likes=card.likes, dislikes=card.dislikes),
        )
        await scope.image_catalog_uc.mark_shown(
            chat_id=chat.id,
            image_id=card.id,
            at=at,
        )

    await run_message_handler(message, scope.logger, _action)


@generation_router.message(Command("generate"))
async def cmd_generate(
    message: Message,
    command: CommandObject,
    user: UserContext,
    chat: ChatContext,
    scope: RequestScope,
) -> None:
    """Generate an image from a user prompt or a random LLM prompt."""

    async def _action() -> None:
        at = message.date
        logger = scope.logger.bind(module="generation_router")
        raw_prompt = (command.args or "").strip() or None

        snap = await scope.user_generation_uc.begin_generation(user_id=user.id, at=at)
        status = await message.answer(generation_msg.GENERATION_STARTED)
        committed = False

        try:
            render = await scope.image_generation_uc.generate(
                vendor=user.model_vendor,
                model=user.model,
                prompt=raw_prompt,
            )
            sent = await message.answer_photo(
                photo=BufferedInputFile(render.content, filename="wednesday.png"),
            )
            if not sent.photo:
                logger.error("Telegram returned photo message without photo sizes")
                return
            card = await scope.image_generation_uc.register(
                file_id=sent.photo[-1].file_id,
                author_id=user.id,
                model=user.model,
                prompts=render.prompts,
                chat_id=chat.id,
                at=at,
            )
            await sent.edit_reply_markup(
                reply_markup=build_vote_kb(image_id=card.id, likes=card.likes, dislikes=card.dislikes),
            )
            committed = True
        except PromptRejectedError as exc:
            logger.warning("Prompt rejected, assigning ban")
            await scope.user_moderation_uc.assign_ban(user_id=user.id, at=at)
            await status.edit_text(user_message_for_exception(exc))
            return
        finally:
            if not committed:
                await scope.user_generation_uc.refund_generation(user_id=user.id, snapshot=snap)

        try:
            await status.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            logger.debug("Failed to delete generate status message", exc_info=True)

    await run_message_handler(message, scope.logger, _action)

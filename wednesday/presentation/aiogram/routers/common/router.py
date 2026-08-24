"""Handlers for common commands: /start, /help."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.protocols import Logger

from .messages import HELP, UNKNOWN_COMMAND, WELCOME

common_router = Router(name="common")


@common_router.message(CommandStart())
async def cmd_start(
    message: Message,
    logger: Logger,
) -> None:
    """Welcome message and command list."""
    logger.info("Command /start", user_id=message.from_user.id if message.from_user else None)
    await message.reply(text=WELCOME)


@common_router.message(Command("help"))
async def cmd_help(
    message: Message,
    logger: Logger,
) -> None:
    """Command help."""
    logger.info("Command /help", user_id=message.from_user.id if message.from_user else None)
    await message.reply(text=HELP)


@common_router.message(F.text.startswith("/"))
async def cmd_unknown(
    message: Message,
    logger: Logger,
) -> None:
    """Any unknown command (registered after specific commands)."""
    logger.info("Unknown command", user_id=message.from_user.id if message.from_user else None)
    await message.reply(text=UNKNOWN_COMMAND)

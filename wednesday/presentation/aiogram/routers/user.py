"""Handlers for user commands: /generate."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.dto import UserContext

from ..filters import InsufficientCommandArgs, RequireCommandArgs
from ..messages import commands as cmd_msg, profile as profile_msg

user_router = Router(name="user")


@user_router.message(Command("me"))
async def cmd_me(message: Message, user: UserContext) -> None:
    """Show caller role, subscription, and ban status from registration context."""
    await message.answer(text=profile_msg.format_me(user))


@user_router.message(Command("generate"))
async def cmd_generate(message: Message) -> None:
    """Start image generation: status message and enqueue."""
    await message.answer(text=cmd_msg.WIP)


@user_router.message(Command("set_model"), InsufficientCommandArgs())
async def cmd_set_model_usage(message: Message) -> None:
    await message.answer(cmd_msg.SET_MODEL_USAGE)


@user_router.message(Command("set_model"), RequireCommandArgs())
async def cmd_set_model(message: Message) -> None:
    """Set GigaChat image model."""
    await message.answer(text=cmd_msg.WIP)


@user_router.message(Command("list_models"))
async def cmd_list_models(message: Message) -> None:
    """List available image generation models."""
    await message.answer(text=cmd_msg.WIP)

from aiogram import Router

from .generation import cmd_generate, cmd_random, generation_router
from .reset import ResetViewsData, cb_reset_views, cmd_reset, reset_router
from .vote import ImageVoteData, build_vote_kb, cb_image_vote, edit_vote_markup, vote_router

image_router = Router(name="image")

image_router.include_router(generation_router)
image_router.include_router(vote_router)
image_router.include_router(reset_router)


__all__ = [
    "ImageVoteData",
    "ResetViewsData",
    "build_vote_kb",
    "cb_image_vote",
    "cb_reset_views",
    "cmd_generate",
    "cmd_random",
    "cmd_reset",
    "edit_vote_markup",
    "generation_router",
    "image_router",
    "reset_router",
    "vote_router",
]

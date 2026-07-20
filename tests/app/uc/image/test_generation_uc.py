"""Tests for ImageGenerationUseCase."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.dto import ImageCard
from app.use_cases.image import ImageGenerationUseCase
from domain.catalog import Model
from domain.image import (
    ImagePrompts,
    ImageRender,
    NormalizedPrompt,
    PromptModerationPolicy,
    PromptRejectedError,
    PromptSource,
    TelegramFileId,
)
from domain.kernel.vo import AwareDatetime
from tests.dom.image.factories import (
    FakeImageGenerator,
    FakeImageRepo,
    FakePromptCatalog,
    FakeTextGenerator,
)

from ...factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def _make_uc(
    *,
    uow: FakeUoW | None = None,
    txt_gen: FakeTextGenerator | None = None,
    img_gen: FakeImageGenerator | None = None,
) -> ImageGenerationUseCase:
    return ImageGenerationUseCase(
        uow=uow or FakeUoW(),
        prompts=FakePromptCatalog(),
        txt_gen=txt_gen or FakeTextGenerator(response="enriched frog"),
        img_gen=img_gen or FakeImageGenerator(content=b"png"),
        moderation=PromptModerationPolicy(),
        logger=mk_logger(),
    )


def _mk_render(*, content: bytes = b"png") -> ImageRender:
    return ImageRender(
        content=content,
        prompts=ImagePrompts(
            primary=NormalizedPrompt.parse("frog meme"),
            source=PromptSource.USER,
        ),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_by_user_returns_render() -> None:
    uc = _make_uc()

    render = await uc.by_user(
        model=Model.parse("gigachat-2-lite"),
        user_input=NormalizedPrompt.parse("frog meme"),
    )

    assert isinstance(render, ImageRender)
    assert render.content == b"png"
    assert render.prompts.source == PromptSource.USER


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_by_user_rejects_banned_prompt() -> None:
    uc = _make_uc()

    with pytest.raises(PromptRejectedError):
        await uc.by_user(
            model=Model.parse("gigachat-2-lite"),
            user_input=NormalizedPrompt.parse("naked frog"),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_random_returns_render() -> None:
    uc = _make_uc(
        txt_gen=FakeTextGenerator(response="random frog"),
        img_gen=FakeImageGenerator(content=b"rnd"),
    )

    render = await uc.random(model=Model.parse("gigachat-2-lite"))

    assert isinstance(render, ImageRender)
    assert render.content == b"rnd"
    assert render.prompts.source == PromptSource.LLM


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_persists_image_in_uow() -> None:
    image_repo = FakeImageRepo()
    uow = FakeUoW(images=image_repo)
    uc = _make_uc(uow=uow)
    render = _mk_render()
    file_id = TelegramFileId.parse("AgACAgIAAxkBAAI")
    author_id = UUID(int=42)
    model = Model.parse("gigachat-2-lite")

    card = await uc.register(
        render=render,
        file_id=file_id,
        author_id=author_id,
        model=model,
        at=dt(12),
    )

    assert isinstance(card, ImageCard)
    assert card.file_id == file_id
    assert uow.enter_count == uow.exit_count == 1
    saved = await image_repo.get_by_id(card.id)
    assert saved is not None
    assert saved.meta.author_id == author_id
    assert saved.meta.model == model
    assert saved.prompts == render.prompts

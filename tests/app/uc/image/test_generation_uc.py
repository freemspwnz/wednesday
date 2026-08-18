"""Tests for ImageGenerationUseCase."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest

from app.dto import ImageCard
from app.protocols import Logger
from app.use_cases.image import ImageCatalogUseCase, ImageGenerationUseCase
from domain.catalog import Model
from domain.chat import ChatId
from domain.image import (
    ImageId,
    ImageMeta,
    ImagePrompts,
    ImageRender,
    NormalizedPrompt,
    PromptModerationPolicy,
    PromptRejectedError,
    PromptSource,
    TelegramFileId,
)
from domain.kernel.vo import AwareDatetime
from domain.user import UserId
from tests.dom.image.factories import FakeGenerator, FakeImageRepo, FakePromptCatalog, FakeViewRepo

from ...factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def _make_uc(
    *,
    uow: FakeUoW | None = None,
    gen: FakeGenerator | None = None,
    logger: Logger | None = None,
) -> ImageGenerationUseCase:
    return ImageGenerationUseCase(
        uow=uow or FakeUoW(),
        prompts=FakePromptCatalog(),
        gen=gen or FakeGenerator(text_response="enriched frog", image_content=b"png"),
        policy=PromptModerationPolicy(),
        logger=logger or Mock(spec=Logger),
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
        prompt="frog meme",
    )

    assert isinstance(render, ImageRender)
    assert render.content == b"png"
    assert render.prompts.source == PromptSource.USER


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_by_user_logs_finish_at_info() -> None:
    log = mk_logger()
    uc = _make_uc(logger=log)

    await uc.by_user(model=Model.parse("gigachat-2-lite"), prompt="frog meme")

    log.info.assert_called_once_with(
        "Image generation by user finished",
        model="gigachat-2-lite",
        bytes=3,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_by_user_rejects_banned_prompt() -> None:
    uc = _make_uc()

    with pytest.raises(PromptRejectedError):
        await uc.by_user(
            model=Model.parse("gigachat-2-lite"),
            prompt="naked frog",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_random_returns_render() -> None:
    uc = _make_uc(
        gen=FakeGenerator(text_response="random frog", image_content=b"rnd"),
    )

    render = await uc.random(model=Model.parse("gigachat-2-lite"))

    assert isinstance(render, ImageRender)
    assert render.content == b"rnd"
    assert render.prompts.source == PromptSource.LLM


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_random_logs_finish_at_info() -> None:
    log = mk_logger()
    uc = _make_uc(
        gen=FakeGenerator(text_response="random frog", image_content=b"rnd"),
        logger=log,
    )

    await uc.random(model=Model.parse("gigachat-2-lite"))

    log.info.assert_called_once_with(
        "Random image generation finished",
        model="gigachat-2-lite",
        bytes=3,
    )


async def _register(uc: ImageGenerationUseCase, *, chat_id: ChatId) -> ImageCard:
    return await uc.register(
        image_id=ImageId(UUID(int=77)),
        file_id=TelegramFileId.parse("AgACAgIAAxkBAAI"),
        meta=ImageMeta(author_id=UserId(UUID(int=42)), model=Model.parse("gigachat-2-lite")),
        render=_mk_render(),
        chat_id=chat_id,
        at=dt(12),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_persists_image_and_view_in_uow() -> None:
    image_repo = FakeImageRepo()
    views = FakeViewRepo()
    uow = FakeUoW(images=image_repo, views=views)
    uc = _make_uc(uow=uow)
    chat_id = ChatId(UUID(int=100))
    image_id = ImageId(UUID(int=77))
    author_id = UserId(UUID(int=42))
    model = Model.parse("gigachat-2-lite")

    card = await _register(uc, chat_id=chat_id)

    assert isinstance(card, ImageCard)
    assert card.file_id == TelegramFileId.parse("AgACAgIAAxkBAAI")
    assert card.id == image_id
    assert uow.enter_count == uow.exit_count == 1
    saved = await image_repo.get_by_id(card.id)
    assert saved is not None
    assert saved.meta.author_id == author_id
    assert saved.meta.model == model
    assert saved.prompts == _mk_render().prompts
    assert (chat_id.value, image_id) in views.shown


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_hides_image_from_same_chat_random() -> None:
    image_repo = FakeImageRepo()
    views = FakeViewRepo()
    uow = FakeUoW(images=image_repo, views=views)
    gen_uc = _make_uc(uow=uow)
    catalog_uc = ImageCatalogUseCase(uow=uow, logger=mk_logger())
    chat_id = ChatId(UUID(int=100))
    other_chat_id = ChatId(UUID(int=101))

    card = await _register(gen_uc, chat_id=chat_id)
    saved = await image_repo.get_by_id(card.id)
    assert saved is not None
    views.candidates = [saved]

    assert await catalog_uc.pick_for_chat(chat_id=chat_id, at=dt(13)) is None

    picked = await catalog_uc.pick_for_chat(chat_id=other_chat_id, at=dt(13))
    assert picked is not None
    assert picked.id == card.id

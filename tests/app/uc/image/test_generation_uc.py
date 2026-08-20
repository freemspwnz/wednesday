"""Tests for ImageGenerationUseCase."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest

from app.dto import ImageCard
from app.exceptions import UnknownProviderError
from app.protocols import Logger
from app.use_cases.image import ImageCatalogUseCase, ImageGenerationUseCase
from domain.catalog import Model
from domain.chat import ChatId
from domain.image import (
    ImageId,
    ImagePrompts,
    ImageRender,
    NormalizedPrompt,
    PromptModerationPolicy,
    PromptRejectedError,
    PromptSource,
)
from domain.kernel.vo import AwareDatetime
from domain.user import UserId
from tests.dom.image.factories import (
    FakeGenerator,
    FakeGeneratorRegistry,
    FakeImageRepo,
    FakePromptCatalog,
    FakeViewRepo,
)

from ...factories import FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, tzinfo=UTC))


def _make_uc(
    *,
    uow: FakeUoW | None = None,
    gen: FakeGenerator | None = None,
    registry: FakeGeneratorRegistry | None = None,
    logger: Logger | None = None,
) -> ImageGenerationUseCase:
    if registry is None:
        registry = FakeGeneratorRegistry(
            generator=gen or FakeGenerator(text_response="enriched frog", image_content=b"png"),
        )
    return ImageGenerationUseCase(
        uow=uow or FakeUoW(),
        prompts=FakePromptCatalog(),
        generators=registry,
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
async def test_uc_generate_with_prompt_returns_render() -> None:
    uc = _make_uc()

    render = await uc.generate(
        vendor="sber",
        model="gigachat-2-lite",
        prompt="frog meme",
    )

    assert isinstance(render, ImageRender)
    assert render.content == b"png"
    assert render.prompts.source == PromptSource.USER


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_generate_with_prompt_logs_finish_at_info() -> None:
    log = mk_logger()
    uc = _make_uc(logger=log)

    await uc.generate(vendor="sber", model="gigachat-2-lite", prompt="frog meme")

    log.info.assert_called_once_with(
        "Image generation by user finished",
        model="gigachat-2-lite",
        bytes=3,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_generate_rejects_banned_prompt() -> None:
    uc = _make_uc()

    with pytest.raises(PromptRejectedError):
        await uc.generate(
            vendor="sber",
            model="gigachat-2-lite",
            prompt="naked frog",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_generate_unknown_vendor_raises() -> None:
    uc = _make_uc(registry=FakeGeneratorRegistry(generator=None))

    with pytest.raises(UnknownProviderError):
        await uc.generate(
            vendor="yandex",
            model="gigachat-2-lite",
            prompt="frog meme",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_generate_without_prompt_unknown_vendor_raises() -> None:
    uc = _make_uc(registry=FakeGeneratorRegistry(generator=None))

    with pytest.raises(UnknownProviderError):
        await uc.generate(
            vendor="yandex",
            model="gigachat-2-lite",
            prompt=None,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_generate_without_prompt_returns_render() -> None:
    uc = _make_uc(
        gen=FakeGenerator(text_response="random frog", image_content=b"rnd"),
    )

    render = await uc.generate(vendor="sber", model="gigachat-2-lite", prompt=None)

    assert isinstance(render, ImageRender)
    assert render.content == b"rnd"
    assert render.prompts.source == PromptSource.LLM


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_generate_without_prompt_logs_finish_at_info() -> None:
    log = mk_logger()
    uc = _make_uc(
        gen=FakeGenerator(text_response="random frog", image_content=b"rnd"),
        logger=log,
    )

    await uc.generate(vendor="sber", model="gigachat-2-lite", prompt=None)

    log.info.assert_called_once_with(
        "Random image generation finished",
        model="gigachat-2-lite",
        bytes=3,
    )


async def _register(uc: ImageGenerationUseCase, *, chat_id: ChatId) -> ImageCard:
    return await uc.register(
        file_id="AgACAgIAAxkBAAI",
        author_id=str(UserId(UUID(int=42))),
        model="gigachat-2-lite",
        prompts=_mk_render().prompts,
        chat_id=str(chat_id),
        at=dt(12).value,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_persists_image_and_view_in_uow() -> None:
    image_repo = FakeImageRepo()
    views = FakeViewRepo()
    uow = FakeUoW(images=image_repo, views=views)
    uc = _make_uc(uow=uow)
    chat_id = ChatId(UUID(int=100))
    author_id = UserId(UUID(int=42))
    model = Model.parse("gigachat-2-lite")

    card = await _register(uc, chat_id=chat_id)

    assert isinstance(card, ImageCard)
    assert card.file_id == "AgACAgIAAxkBAAI"
    assert card.likes >= 0
    assert uow.enter_count == uow.exit_count == 1
    saved = await image_repo.get_by_id(ImageId(UUID(card.id)))
    assert saved is not None
    assert saved.meta.author_id == author_id
    assert saved.meta.model == model
    assert saved.prompts == _mk_render().prompts
    assert (chat_id.value, saved.id) in views.shown


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
    saved = await image_repo.get_by_id(ImageId(UUID(card.id)))
    assert saved is not None
    views.candidates = [saved]

    assert await catalog_uc.pick_for_chat(chat_id=str(chat_id)) is None

    picked = await catalog_uc.pick_for_chat(chat_id=str(other_chat_id))
    assert picked is not None
    assert picked.id == card.id

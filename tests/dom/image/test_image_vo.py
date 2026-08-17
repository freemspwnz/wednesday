from collections.abc import Callable

import pytest

from domain.catalog import Model, ModelDescriptor, Series, SubscriptionTier, Vendor
from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    ImageId,
    ImageMeta,
    ImagePrompts,
    ImageRender,
    NormalizedPrompt,
    PromptSource,
    TelegramFileId,
)
from domain.image.exceptions import ValidationError
from domain.image.protocols.catalog import PromptComponents

from .factories import mk_meta, mk_prompts


@pytest.mark.unit
def test_image_meta_and_ensure() -> None:
    meta = mk_meta(author_id=1)
    assert meta.model == Model.parse("gigachat-2-lite")
    assert ImageMeta.ensure(meta) is meta


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  hello   world  ", "hello world"),
        ("frog", "frog"),
    ],
)
def test_normalized_prompt_parse(raw: str, expected: str) -> None:
    assert str(NormalizedPrompt.parse(raw)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: NormalizedPrompt.parse(""), "prompt cannot be empty"),
        (lambda: NormalizedPrompt.parse("x" * 1001), "prompt exceeds max length"),
        (lambda: NormalizedPrompt(value="  spaced"), "prompt must be normalized"),
    ],
)
def test_normalized_prompt_rejects_invalid(factory: Callable[[], None], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        factory()


@pytest.mark.unit
def test_telegram_file_id_parse_and_ensure() -> None:
    file_id = TelegramFileId.parse("  AgACAgIAAxkBAAI  ")
    assert str(file_id) == "AgACAgIAAxkBAAI"
    assert TelegramFileId.ensure(file_id) is file_id


@pytest.mark.unit
@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: TelegramFileId.parse("   "), "telegram file id cannot be empty"),
        (lambda: TelegramFileId.parse("x" * 257), "telegram file id exceeds max length"),
    ],
)
def test_telegram_file_id_rejects_invalid(factory: Callable[[], None], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        factory()


@pytest.mark.unit
def test_image_state_types() -> None:
    state = HiddenState(reason=HiddenReason.ADMIN)
    assert isinstance(state, HiddenState)
    assert state.reason == HiddenReason.ADMIN
    assert isinstance(ActiveState(), ActiveState)


@pytest.mark.unit
def test_image_prompts_effective_and_validation() -> None:
    prompts = mk_prompts(primary="user", enriched="enriched")
    assert str(prompts.effective()) == "enriched"

    with pytest.raises(ValidationError, match="enriched prompt is not allowed"):
        ImagePrompts(
            primary=NormalizedPrompt.parse("llm"),
            source=PromptSource.LLM,
            enriched=NormalizedPrompt.parse("bad"),
        )


@pytest.mark.unit
def test_image_render_validation() -> None:
    render = ImageRender(content=b"png", prompts=mk_prompts())
    assert ImageRender.ensure(render) is render

    with pytest.raises(ValidationError, match="content cannot be empty"):
        ImageRender(content=b"", prompts=mk_prompts())


@pytest.mark.unit
def test_image_id_new_and_ensure() -> None:
    image_id = ImageId.new()
    assert image_id.value.version == 7
    assert ImageId.ensure(image_id) is image_id


@pytest.mark.unit
def test_image_id_accepts_existing_v4() -> None:
    from uuid import uuid4

    legacy = ImageId(value=uuid4())
    assert legacy.value.version == 4
    assert ImageId.ensure(legacy) is legacy


@pytest.mark.unit
def test_prompt_components_validation() -> None:
    with pytest.raises(ValidationError, match="heroes must be a non-empty tuple"):
        PromptComponents(
            heroes=(),
            colors=("green",),
            styles=("meme",),
            professions=("coder",),
            actions=("coding",),
            places=("swamp",),
            portraits=("portrait",),
        )


@pytest.mark.unit
def test_model_descriptor_validation_lives_in_catalog() -> None:
    descriptor = ModelDescriptor(
        model=Model.parse("gigachat-2-lite"),
        vendor=Vendor.parse("sber"),
        series=Series.parse("gigachat"),
        display_name="GigaChat 2 Lite",
        min_tier=SubscriptionTier.FREE,
    )
    assert descriptor.active

    with pytest.raises(ValidationError):
        ModelDescriptor(
            model=Model.parse("gigachat-2-lite"),
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            display_name="   ",
            min_tier=SubscriptionTier.FREE,
        )

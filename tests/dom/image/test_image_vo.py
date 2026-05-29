from uuid import UUID

import pytest

from domain.catalog import Model, ModelDescriptor, Series, SubscriptionTier, Vendor
from domain.image import ActiveStatus, HiddenStatus, ImageMeta, NormalizedPrompt, TelegramFileId
from domain.image.exceptions import ValidationError
from domain.image.vo.states import HiddenReason


@pytest.mark.unit
def test_image_meta_create_and_ensure() -> None:
    meta = ImageMeta.create(
        author_id=UUID(int=1),
        model=Model.parse("gigachat-2-lite"),
    )
    assert meta.model == Model.parse("gigachat-2-lite")
    assert ImageMeta.ensure(meta) is meta


@pytest.mark.unit
def test_normalized_prompt_parse() -> None:
    prompt = NormalizedPrompt.parse("  hello   world  ")
    assert str(prompt) == "hello world"


@pytest.mark.unit
def test_telegram_file_id_parse() -> None:
    file_id = TelegramFileId.parse("  AgACAgIAAxkBAAI  ")
    assert str(file_id) == "AgACAgIAAxkBAAI"


@pytest.mark.unit
def test_image_status_types() -> None:
    status = HiddenStatus(reason=HiddenReason.ADMIN)
    assert isinstance(status, HiddenStatus)
    assert status.reason == HiddenReason.ADMIN
    assert isinstance(ActiveStatus(), ActiveStatus)


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

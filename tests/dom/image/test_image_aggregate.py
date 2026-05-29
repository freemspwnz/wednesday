import pytest

from domain.image import ActiveStatus, HiddenStatus, Image, TelegramFileId
from domain.image.exceptions import InvalidStateTransitionError, ValidationError
from domain.image.vo.states import HiddenReason

from .factories import dt, mk_image


@pytest.mark.unit
def test_image_register_restore_and_ensure() -> None:
    image = mk_image(created_at=dt(10))
    assert image.score == 3
    assert image.is_selectable
    assert isinstance(image.status, ActiveStatus)
    assert image.file_id is None
    assert image.prompts is not None
    assert image.prompts.enriched is not None

    restored = Image.restore(
        id=image.id,
        meta=image.meta,
        created_at=image.created_at,
        score=image.score,
        status=image.status,
        prompts=image.prompts,
    )
    assert Image.ensure(restored) is restored


@pytest.mark.unit
def test_image_attach_file_id_once() -> None:
    image = mk_image()
    image.pull_events()
    file_id = TelegramFileId.parse("AgACAgIAAxkBAAI")

    image.attach_file_id(file_id, at=dt(11))
    assert image.file_id == file_id

    with pytest.raises(InvalidStateTransitionError):
        image.attach_file_id(TelegramFileId.parse("other-file-id"), at=dt(12))


@pytest.mark.unit
def test_image_recalculate_score_restores_active_status() -> None:
    base = mk_image(score=0)
    image = Image.restore(
        id=base.id,
        meta=base.meta,
        created_at=base.created_at,
        score=0,
        status=HiddenStatus(reason=HiddenReason.VOTES),
    )
    image.pull_events()

    image.recalculate_score([1, 1], at=dt(13))
    assert image.score == 5
    assert isinstance(image.status, ActiveStatus)
    assert image.is_selectable


@pytest.mark.unit
def test_image_admin_hide_and_restore() -> None:
    image = mk_image()
    image.pull_events()

    image.admin_hide(at=dt(11))
    assert image.score == 0
    assert isinstance(image.status, HiddenStatus)
    assert image.status.reason == HiddenReason.ADMIN
    assert image.is_hidden
    assert not image.is_selectable

    image.admin_restore(at=dt(12))
    assert image.score == 3
    assert isinstance(image.status, ActiveStatus)
    assert image.is_selectable


@pytest.mark.unit
def test_image_register_custom_score() -> None:
    image = mk_image(score=5)
    assert image.score == 5


@pytest.mark.unit
def test_image_validate_rejects_incoherent_state() -> None:
    with pytest.raises(ValidationError):
        Image.restore(
            id=mk_image().id,
            meta=mk_image().meta,
            created_at=dt(10),
            score=3,
            status=HiddenStatus(reason=HiddenReason.VOTES),
        )

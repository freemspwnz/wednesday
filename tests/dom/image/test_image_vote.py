import pytest

from domain.image.exceptions import ValidationError
from domain.image.vote import Vote

from .factories import mk_image, mk_user_id


@pytest.mark.unit
def test_vote_accepts_plus_one_and_minus_one() -> None:
    image = mk_image()
    voter_id = mk_user_id(2)

    plus = Vote(image_id=image.id, voter_id=voter_id, value=1)
    minus = plus.change(-1)

    assert plus.value == 1
    assert minus.value == -1


@pytest.mark.unit
def test_vote_rejects_invalid_value() -> None:
    image = mk_image()
    with pytest.raises(ValidationError):
        Vote(image_id=image.id, voter_id=mk_user_id(2), value=0)

    vote = Vote(image_id=image.id, voter_id=mk_user_id(2), value=1)
    with pytest.raises(ValidationError):
        vote.change(2)


@pytest.mark.unit
def test_vote_rejects_bad_voter_id() -> None:
    image = mk_image()
    with pytest.raises(ValidationError):
        Vote(image_id=image.id, voter_id="bad", value=1)  # type: ignore[arg-type]

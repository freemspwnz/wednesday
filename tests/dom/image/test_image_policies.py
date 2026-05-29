import pytest

from domain.image import ImageScorePolicy
from domain.image.exceptions import ValidationError


@pytest.mark.unit
def test_image_score_policy_compute() -> None:
    assert ImageScorePolicy.compute([]) == 3
    assert ImageScorePolicy.compute([1, 1, -1]) == 4
    assert ImageScorePolicy.compute([-1, -1, -1, -1]) == -1


@pytest.mark.unit
def test_image_score_policy_hidden_and_selectable() -> None:
    assert ImageScorePolicy.is_hidden(0)
    assert ImageScorePolicy.is_hidden(-1)
    assert not ImageScorePolicy.is_hidden(1)

    assert ImageScorePolicy.is_selectable(1)
    assert not ImageScorePolicy.is_selectable(0)


@pytest.mark.unit
def test_image_score_policy_rejects_invalid_vote() -> None:
    with pytest.raises(ValidationError):
        ImageScorePolicy.compute([2])

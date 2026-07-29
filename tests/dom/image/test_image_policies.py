"""Tests for image rating and other image policies."""

import pytest

from domain.image import (
    ActiveState,
    HiddenReason,
    HiddenState,
    Hide,
    HideImage,
    ImageRating,
    ImageRatingPolicy,
    ManagementAccessCode,
    ManagementAccessPolicy,
    ManagementAction,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
    ModerationAllowed,
    ModerationCode,
    ModerationDenied,
    NoOperation,
    PromptModerationPolicy,
    Show,
    ShowImage,
    ValidationError,
)
from domain.user import UserRole

from .factories import mk_rating


@pytest.mark.unit
def test_image_rating_policy_default() -> None:
    assert ImageRatingPolicy.default() == ImageRating(likes=3, dislikes=0)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rating", "new", "old", "expected"),
    [
        (mk_rating(likes=3), 1, None, mk_rating(likes=4)),
        (mk_rating(likes=3), -1, None, mk_rating(likes=3, dislikes=1)),
        (mk_rating(likes=4), -1, 1, mk_rating(likes=3, dislikes=1)),
        (mk_rating(likes=3, dislikes=1), 1, -1, mk_rating(likes=4)),
        (mk_rating(likes=4), 1, 1, mk_rating(likes=4)),
    ],
)
def test_image_rating_policy_add_vote(
    rating: ImageRating,
    new: int,
    old: int | None,
    expected: ImageRating,
) -> None:
    assert ImageRatingPolicy.add_vote(rating, new, old) == expected


@pytest.mark.unit
def test_image_rating_policy_add_vote_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        ImageRatingPolicy.add_vote(mk_rating(), 2, None)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rating", "selectable"),
    [
        (mk_rating(likes=0), True),
        (mk_rating(likes=0, dislikes=1), False),
        (mk_rating(likes=3), True),
    ],
)
def test_image_rating_policy_is_selectable(rating: ImageRating, selectable: bool) -> None:
    assert ImageRatingPolicy.is_selectable(rating) is selectable


@pytest.mark.unit
def test_image_rating_policy_evaluate() -> None:
    active = ActiveState()
    assert isinstance(
        ImageRatingPolicy.evaluate(mk_rating(likes=3), active),
        Show,
    )
    assert isinstance(
        ImageRatingPolicy.evaluate(mk_rating(likes=0, dislikes=1), active),
        Hide,
    )
    assert isinstance(
        ImageRatingPolicy.evaluate(
            mk_rating(likes=0, dislikes=1),
            HiddenState(reason=HiddenReason.ADMIN),
        ),
        NoOperation,
    )


@pytest.mark.unit
def test_image_rating_policy_on_show() -> None:
    current = mk_rating(likes=1, dislikes=2)
    assert ImageRatingPolicy.on_show(UserRole.SYSTEM, current) == current
    assert ImageRatingPolicy.on_show(UserRole.OWNER, current) == ImageRatingPolicy.default()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "allowed"),
    [
        ("cute frog", True),
        ("naked frog", False),
        ("", True),
        ("blood on floor", False),
    ],
)
def test_prompt_moderation_policy(text: str, allowed: bool) -> None:
    policy = PromptModerationPolicy()
    decision = policy.evaluate(text)
    if allowed:
        assert isinstance(decision, ModerationAllowed)
    else:
        assert isinstance(decision, ModerationDenied)
        assert decision.violation.code == ModerationCode.PROHIBITED_CONTENT


@pytest.mark.unit
def test_prompt_moderation_policy_requires_banned_words() -> None:
    with pytest.raises(ValidationError, match="banned_words cannot be empty"):
        PromptModerationPolicy(banned_words=["", "   "])


@pytest.mark.unit
@pytest.mark.parametrize(
    ("actor", "action", "allowed"),
    [
        (UserRole.ADMIN, HideImage(), True),
        (UserRole.ADMIN, ShowImage(), False),
        (UserRole.OWNER, HideImage(), True),
        (UserRole.OWNER, ShowImage(), True),
        (UserRole.SYSTEM, ShowImage(), True),
        (UserRole.USER, HideImage(), False),
        (UserRole.USER, ShowImage(), False),
    ],
)
def test_management_access_policy(actor: UserRole, action: ManagementAction, allowed: bool) -> None:
    decision = ManagementAccessPolicy.evaluate(ManagementContext(actor=actor, action=action))
    if allowed:
        assert isinstance(decision, ManagementAllowed)
    else:
        assert isinstance(decision, ManagementDenied)
        assert decision.code == ManagementAccessCode.ACCESS_DENIED

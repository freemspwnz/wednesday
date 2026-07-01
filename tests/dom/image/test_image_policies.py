import pytest

from domain.image import ImageScorePolicy
from domain.image.exceptions import ValidationError
from domain.image.policies import (
    HideImage,
    ManagementAccessCode,
    ManagementAccessPolicy,
    ManagementAction,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
    ModerationAllowed,
    ModerationCode,
    ModerationDenied,
    PromptModerationPolicy,
    ShowImage,
)
from domain.user.vo import UserRole


@pytest.mark.unit
@pytest.mark.parametrize(
    ("votes", "expected"),
    [
        ([], 3),
        ([1, 1, -1], 4),
        ([-1, -1, -1, -1], -1),
    ],
)
def test_image_score_policy_compute(votes: list[int], expected: int) -> None:
    assert ImageScorePolicy.compute(votes) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "hidden", "selectable"),
    [
        (0, True, False),
        (-1, True, False),
        (1, False, True),
    ],
)
def test_image_score_policy_hidden_and_selectable(score: int, hidden: bool, selectable: bool) -> None:
    assert ImageScorePolicy.is_hidden(score) is hidden
    assert ImageScorePolicy.is_selectable(score) is selectable


@pytest.mark.unit
def test_image_score_policy_rejects_invalid_vote() -> None:
    with pytest.raises(ValidationError):
        ImageScorePolicy.compute([2])


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

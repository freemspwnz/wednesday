from uuid import UUID

import pytest

from domain.chat import (
    ChatId,
    ChatMember,
    ChatMemberId,
    ChatMemberRole,
    ManagementContext,
    System,
)
from domain.chat.policies import (
    ManagementAccessCode,
    ManagementAccessPolicy,
    ManagementAllowed,
    ManagementDenied,
)


def cid(n: int = 1) -> ChatId:
    return ChatId(value=UUID(int=n))


@pytest.mark.unit
def test_management_policy_allows_system_actor() -> None:
    ctx = ManagementContext(actor=System(), chat_id=cid())
    decision = ManagementAccessPolicy.evaluate(ctx)
    assert isinstance(decision, ManagementAllowed)


@pytest.mark.unit
def test_management_policy_allows_owner() -> None:
    ch = cid()
    ctx = ManagementContext(
        actor=ChatMember(id=ChatMemberId(1), role=ChatMemberRole.OWNER, chat_id=ch),
        chat_id=ch,
    )
    decision = ManagementAccessPolicy.evaluate(ctx)
    assert isinstance(decision, ManagementAllowed)


@pytest.mark.unit
def test_management_policy_allows_admin() -> None:
    ch = cid()
    ctx = ManagementContext(
        actor=ChatMember(id=ChatMemberId(2), role=ChatMemberRole.ADMIN, chat_id=ch),
        chat_id=ch,
    )
    decision = ManagementAccessPolicy.evaluate(ctx)
    assert isinstance(decision, ManagementAllowed)


@pytest.mark.unit
def test_management_policy_denies_member() -> None:
    ch = cid()
    ctx = ManagementContext(
        actor=ChatMember(id=ChatMemberId(3), role=ChatMemberRole.MEMBER, chat_id=ch),
        chat_id=ch,
    )
    decision = ManagementAccessPolicy.evaluate(ctx)
    assert isinstance(decision, ManagementDenied)
    assert decision.code is ManagementAccessCode.NOT_ENOUGH_RIGHTS


@pytest.mark.unit
def test_management_policy_denies_restricted() -> None:
    ch = cid()
    ctx = ManagementContext(
        actor=ChatMember(
            id=ChatMemberId(4),
            role=ChatMemberRole.RESTRICTED,
            chat_id=ch,
        ),
        chat_id=ch,
    )
    decision = ManagementAccessPolicy.evaluate(ctx)
    assert isinstance(decision, ManagementDenied)
    assert decision.code is ManagementAccessCode.NOT_ENOUGH_RIGHTS


@pytest.mark.unit
def test_management_policy_denies_actor_chat_mismatch_even_for_owner() -> None:
    ctx = ManagementContext(
        actor=ChatMember(
            id=ChatMemberId(1),
            role=ChatMemberRole.OWNER,
            chat_id=cid(1),
        ),
        chat_id=cid(2),
    )
    decision = ManagementAccessPolicy.evaluate(ctx)
    assert isinstance(decision, ManagementDenied)
    assert decision.code is ManagementAccessCode.ACTOR_CHAT_MISMATCH


@pytest.mark.unit
def test_management_policy_unknown_actor_branch_returns_unknown_code() -> None:
    """Defensive branch: actor is neither System nor ChatMember.

    Bypassing the normal constructor since ManagementContext validates actor type.
    """
    ctx = object.__new__(ManagementContext)
    object.__setattr__(ctx, "actor", object())
    object.__setattr__(ctx, "chat_id", cid())

    decision = ManagementAccessPolicy.evaluate(ctx)
    assert isinstance(decision, ManagementDenied)
    assert decision.code is ManagementAccessCode.UNKNOWN_ACTOR

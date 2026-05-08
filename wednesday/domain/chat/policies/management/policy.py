from typing import ClassVar

from ...vo import ChatMember, ChatMemberRole, System
from .vo import (
    ManagementAccessCode,
    ManagementAccessDecision,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
)


class ManagementAccessPolicy:
    ALLOWED: ClassVar[set[ChatMemberRole]] = {ChatMemberRole.OWNER, ChatMemberRole.ADMIN}

    @classmethod
    def evaluate(cls, ctx: ManagementContext) -> ManagementAccessDecision:
        match ctx.actor:
            case System():
                return cls.allow()
            case ChatMember():
                if ctx.actor.chat_id != ctx.chat_id:
                    return cls.deny(ManagementAccessCode.ACTOR_CHAT_MISMATCH)
                if ctx.actor.role not in cls.ALLOWED:
                    return cls.deny(ManagementAccessCode.NOT_ENOUGH_RIGHTS)
                return cls.allow()
            case _:
                return cls.deny(ManagementAccessCode.UNKNOWN_ACTOR)

    @classmethod
    def allow(cls) -> ManagementAllowed:
        return ManagementAllowed()

    @classmethod
    def deny(cls, code: ManagementAccessCode) -> ManagementDenied:
        return ManagementDenied(code)

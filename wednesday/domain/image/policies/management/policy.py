from typing import ClassVar

from domain.user import UserRole

from .vo import (
    HideImage,
    ManagementAccessCode,
    ManagementAccessDecision,
    ManagementAction,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
    ShowImage,
)


class ManagementAccessPolicy:
    """Policy for checking if an actor may hide or show catalog images."""

    matrix: ClassVar[dict[UserRole, set[type[ManagementAction]]]] = {
        UserRole.ADMIN: {HideImage},
        UserRole.OWNER: {HideImage, ShowImage},
        UserRole.SYSTEM: {HideImage, ShowImage},
    }

    @classmethod
    def evaluate(cls, ctx: ManagementContext) -> ManagementAccessDecision:
        actions = cls.matrix.get(ctx.actor)
        if actions is None:
            return cls.deny(ManagementAccessCode.ACCESS_DENIED)

        if not any(isinstance(ctx.action, allowed) for allowed in actions):
            return cls.deny(ManagementAccessCode.ACCESS_DENIED)

        return cls.allow()

    @classmethod
    def allow(cls) -> ManagementAllowed:
        return ManagementAllowed()

    @classmethod
    def deny(cls, code: ManagementAccessCode) -> ManagementDenied:
        return ManagementDenied(code)

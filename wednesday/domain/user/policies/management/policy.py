from typing import ClassVar

from ...vo import UserRole
from .vo import (
    ManagementAccessAllowed,
    ManagementAccessCode,
    ManagementAccessContext,
    ManagementAccessDecision,
    ManagementAccessDenied,
)


class ManagementAccessPolicy:
    """Policy for checking if an actor is allowed to access management commands."""

    matrix: ClassVar[dict[UserRole, set[UserRole]]] = {
        UserRole.ADMIN: {UserRole.USER},
        UserRole.OWNER: {UserRole.USER, UserRole.ADMIN},
        UserRole.SYSTEM: {UserRole.USER, UserRole.ADMIN, UserRole.OWNER},
    }

    @classmethod
    def evaluate(cls, ctx: ManagementAccessContext) -> ManagementAccessDecision:
        if ctx.actor_role not in cls.matrix:
            return cls.deny(ManagementAccessCode.NOT_ENOUGH_RIGHTS)

        if ctx.target_role not in cls.matrix[ctx.actor_role]:
            return cls.deny(ManagementAccessCode.TARGET_UNMANAGEABLE)

        return cls.allow()

    @classmethod
    def allow(cls) -> ManagementAccessAllowed:
        return ManagementAccessAllowed()

    @classmethod
    def deny(cls, code: ManagementAccessCode) -> ManagementAccessDenied:
        return ManagementAccessDenied(code)

from typing import ClassVar

from ...vo import UserRole
from .vo import (
    Ban,
    ChangeProfile,
    ChangeRole,
    ChangeSubscription,
    ManagementAccessCode,
    ManagementAccessDecision,
    ManagementAction,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
    Unban,
)


class ManagementAccessPolicy:
    """Policy for checking if an actor is allowed to access management commands."""

    matrix: ClassVar[dict[UserRole, dict[UserRole, set[type[ManagementAction]]]]] = {
        UserRole.ADMIN: {
            UserRole.USER: {Ban, Unban, ChangeSubscription},
        },
        UserRole.OWNER: {
            UserRole.USER: {Ban, Unban, ChangeSubscription, ChangeRole},
            UserRole.ADMIN: {Ban, Unban, ChangeSubscription, ChangeRole},
        },
        UserRole.SYSTEM: {
            UserRole.USER: {Ban, Unban, ChangeSubscription, ChangeRole, ChangeProfile},
            UserRole.ADMIN: {Ban, Unban, ChangeSubscription, ChangeRole, ChangeProfile},
            UserRole.OWNER: {Ban, Unban, ChangeSubscription, ChangeRole, ChangeProfile},
        },
    }

    @classmethod
    def evaluate(cls, ctx: ManagementContext) -> ManagementAccessDecision:
        targets = cls.matrix.get(ctx.actor_role)
        if targets is None:
            return cls.deny(ManagementAccessCode.ACCESS_DENIED)

        actions = targets.get(ctx.target_role)
        if actions is None:
            return cls.deny(ManagementAccessCode.ACCESS_DENIED)

        if not any(isinstance(ctx.action, allowed) for allowed in actions):
            return cls.deny(ManagementAccessCode.ACCESS_DENIED)

        match ctx.action:
            case ChangeRole(old_role=old_role, new_role=new_role):
                # sanity: context должен совпадать с action
                if old_role != ctx.target_role:
                    return cls.deny(ManagementAccessCode.ACCESS_DENIED)

                if new_role >= ctx.actor_role:
                    return cls.deny(ManagementAccessCode.ACCESS_DENIED)

                return cls.allow()

            case ChangeSubscription(old_subscription=old_subscription, new_subscription=new_subscription):
                old_tier = old_subscription.plan.tier
                new_tier = new_subscription.plan.tier

                if ctx.actor_role >= UserRole.OWNER:
                    return cls.allow()

                if new_tier < old_tier:
                    return cls.deny(ManagementAccessCode.ACCESS_DENIED)

                return cls.allow()

            case Ban():
                return cls.allow()

            case Unban():
                return cls.allow()

            case ChangeProfile():
                return cls.allow()

            case _:
                return cls.deny(ManagementAccessCode.ACCESS_DENIED)

    @classmethod
    def allow(cls) -> ManagementAllowed:
        return ManagementAllowed()

    @classmethod
    def deny(cls, code: ManagementAccessCode) -> ManagementDenied:
        return ManagementDenied(code)

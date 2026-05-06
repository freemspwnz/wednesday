from typing import ClassVar

from ...vo import UserRole
from .vo import (
    ChangeProfile,
    ChangeRole,
    ChangeState,
    ChangeSubscription,
    ManagementAccessCode,
    ManagementAccessDecision,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
)


class ManagementAccessPolicy:
    """Policy for checking if an actor is allowed to access management commands."""

    matrix: ClassVar[dict[UserRole, dict[UserRole, set[type]]]] = {
        UserRole.ADMIN: {
            UserRole.USER: {ChangeState, ChangeSubscription},
        },
        UserRole.OWNER: {
            UserRole.USER: {ChangeState, ChangeSubscription, ChangeRole},
            UserRole.ADMIN: {ChangeState, ChangeSubscription, ChangeRole},
        },
        UserRole.SYSTEM: {
            UserRole.USER: {ChangeState, ChangeSubscription, ChangeRole, ChangeProfile},
            UserRole.ADMIN: {ChangeState, ChangeSubscription, ChangeRole, ChangeProfile},
            UserRole.OWNER: {ChangeState, ChangeSubscription, ChangeRole, ChangeProfile},
        },
    }

    @classmethod
    def evaluate(cls, ctx: ManagementContext) -> ManagementAccessDecision:
        targets = cls.matrix.get(ctx.actor_role)
        if targets is None:
            return cls.deny(ManagementAccessCode.ACCESS_DENIED)

        actions = targets.get(ctx.target_role)
        if actions is None:
            return cls.deny(ManagementAccessCode.TARGET_UNMANAGEABLE)

        if type(ctx.action) not in actions:
            return cls.deny(ManagementAccessCode.NOT_ENOUGH_RIGHTS)

        match ctx.action:
            case ChangeRole(old_role=old_role, new_role=new_role):
                # sanity: context должен совпадать с action
                if old_role != ctx.target_role:
                    return cls.deny(ManagementAccessCode.INVALID_CONTEXT)

                if new_role == old_role:
                    return cls.deny(ManagementAccessCode.NO_EFFECT)

                if new_role >= ctx.actor_role:
                    return cls.deny(ManagementAccessCode.NOT_ENOUGH_RIGHTS)

                return cls.allow()

            case ChangeSubscription(old_subscription=old_subscription, new_subscription=new_subscription):
                old_tier = old_subscription.plan.tier
                new_tier = new_subscription.plan.tier

                if old_subscription == new_subscription:
                    return cls.deny(ManagementAccessCode.NO_EFFECT)

                if ctx.actor_role >= UserRole.OWNER:
                    return cls.allow()

                if new_tier < old_tier:
                    return cls.deny(ManagementAccessCode.NOT_ENOUGH_RIGHTS)

                return cls.allow()

            case ChangeState(old_state=old_state, new_state=new_state):
                if old_state == new_state:
                    return cls.deny(ManagementAccessCode.NO_EFFECT)
                return cls.allow()

            case ChangeProfile(old_profile=old_profile, new_profile=new_profile):
                if old_profile == new_profile:
                    return cls.deny(ManagementAccessCode.NO_EFFECT)
                return cls.allow()

            case _:
                return cls.deny(ManagementAccessCode.INVALID_ACTION)

    @classmethod
    def allow(cls) -> ManagementAllowed:
        return ManagementAllowed()

    @classmethod
    def deny(cls, code: ManagementAccessCode) -> ManagementDenied:
        return ManagementDenied(code)

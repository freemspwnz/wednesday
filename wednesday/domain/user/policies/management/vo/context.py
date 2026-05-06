from dataclasses import dataclass

from ....exceptions import ValidationError
from ....vo import UserRole
from .actions import (
    ChangeProfile,
    ChangeRole,
    ChangeState,
    ChangeSubscription,
    ManagementAction,
)


@dataclass(frozen=True)
class ManagementContext:
    """Context for management access policy.

    actor_role: The role of the actor.
    target_role: The role of the target.
    """

    actor_role: UserRole
    target_role: UserRole
    action: ManagementAction

    def __post_init__(self) -> None:
        if not isinstance(self.actor_role, UserRole):
            raise ValidationError("actor_role must be a UserRole")

        if not isinstance(self.target_role, UserRole):
            raise ValidationError("target_role must be a UserRole")

        if not isinstance(self.action, ChangeRole | ChangeSubscription | ChangeState | ChangeProfile):
            raise ValidationError("action must be a ManagementAction")

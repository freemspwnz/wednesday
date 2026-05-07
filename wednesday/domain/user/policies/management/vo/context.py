from dataclasses import dataclass

from ....vo import UserRole
from .actions import ManagementAction


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
        UserRole.ensure(self.actor_role)
        UserRole.ensure(self.target_role)
        ManagementAction.ensure(self.action)

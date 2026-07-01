from dataclasses import dataclass

from domain.user import UserRole

from .actions import ManagementAction


@dataclass(frozen=True)
class ManagementContext:
    """Context for image management access policy."""

    actor: UserRole
    action: ManagementAction

    def __post_init__(self) -> None:
        UserRole.ensure(self.actor)
        ManagementAction.ensure(self.action)

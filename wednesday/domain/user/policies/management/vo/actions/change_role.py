from dataclasses import dataclass

from .....vo import UserRole
from .base import ManagementAction


@dataclass(frozen=True)
class ChangeRole(ManagementAction):
    old_role: UserRole
    new_role: UserRole

    def __post_init__(self) -> None:
        UserRole.ensure(self.old_role)
        UserRole.ensure(self.new_role)

from dataclasses import dataclass

from ....exceptions import ValidationError
from ....vo import UserRole


@dataclass(frozen=True)
class ManagementAccessContext:
    """Context for management access policy.

    actor_role: The role of the actor.
    target_role: The role of the target.
    """

    actor_role: UserRole
    target_role: UserRole

    def __post_init__(self) -> None:
        if not isinstance(self.actor_role, UserRole):
            raise ValidationError("actor_role must be a UserRole")

        if not isinstance(self.target_role, UserRole):
            raise ValidationError("target_role must be a UserRole")

from enum import StrEnum

from ..exceptions import InvalidStateTransitionError


class UserRole(StrEnum):
    SYSTEM = "system"
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"

    def ensure_transition_allowed(self, target: "UserRole") -> None:
        if target not in TRANSITION_MATRIX[self]:
            raise InvalidStateTransitionError("Transition to target role is forbidden.")


TRANSITION_MATRIX: dict[UserRole, set[UserRole]] = {
    UserRole.SYSTEM: set(),
    UserRole.OWNER: {UserRole.ADMIN, UserRole.USER},
    UserRole.ADMIN: {UserRole.OWNER, UserRole.USER},
    UserRole.USER: {UserRole.ADMIN},
}

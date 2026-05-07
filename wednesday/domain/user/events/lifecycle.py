from dataclasses import dataclass

from ..vo import UserProfile, UserRole
from .base import UserEvent


@dataclass(frozen=True)
class UserRoleChanged(UserEvent):
    old_role: UserRole
    new_role: UserRole

    def __post_init__(self) -> None:
        super().__post_init__()

        UserRole.ensure(self.old_role)
        UserRole.ensure(self.new_role)


@dataclass(frozen=True)
class UserProfileChanged(UserEvent):
    old_profile: UserProfile
    new_profile: UserProfile

    def __post_init__(self) -> None:
        super().__post_init__()

        UserProfile.ensure(self.new_profile)
        UserProfile.ensure(self.old_profile)

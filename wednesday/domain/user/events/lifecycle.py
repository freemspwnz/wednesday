from dataclasses import dataclass

from ..vo import UserProfile, UserRole, UserSettings
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


@dataclass(frozen=True)
class UserSettingsChanged(UserEvent):
    old_settings: UserSettings
    new_settings: UserSettings

    def __post_init__(self) -> None:
        super().__post_init__()

        UserSettings.ensure(self.old_settings)
        UserSettings.ensure(self.new_settings)

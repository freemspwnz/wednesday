from dataclasses import dataclass

from ..exceptions import ValidationError
from ..vo import AwareDatetime, UserProfile, UserRole
from .base import UserEvent


@dataclass(frozen=True)
class UserBanned(UserEvent):
    until: AwareDatetime
    actor: UserRole

    def __post_init__(self) -> None:
        super().__post_init__()

        if not isinstance(self.actor, UserRole):
            raise ValidationError("actor must be a UserRole")

        if not isinstance(self.until, AwareDatetime):
            raise ValidationError("until must be a AwareDatetime")


@dataclass(frozen=True)
class UserUnbanned(UserEvent):
    actor: UserRole

    def __post_init__(self) -> None:
        super().__post_init__()

        if not isinstance(self.actor, UserRole):
            raise ValidationError("actor must be a UserRole")


@dataclass(frozen=True)
class UserBanExpired(UserEvent):
    def __post_init__(self) -> None:
        super().__post_init__()


@dataclass(frozen=True)
class UserRoleChanged(UserEvent):
    old_role: UserRole
    new_role: UserRole

    def __post_init__(self) -> None:
        super().__post_init__()

        if not isinstance(self.old_role, UserRole):
            raise ValidationError("old_role must be a UserRole")

        if not isinstance(self.new_role, UserRole):
            raise ValidationError("new_role must be a UserRole")


@dataclass(frozen=True)
class UserProfileChanged(UserEvent):
    old_profile: UserProfile
    new_profile: UserProfile

    def __post_init__(self) -> None:
        super().__post_init__()

        if not isinstance(self.new_profile, UserProfile):
            raise ValidationError("new_profile must be a UserProfile")

        if not isinstance(self.old_profile, UserProfile):
            raise ValidationError("old_profile must be a UserProfile")

from dataclasses import dataclass

from ....exceptions import ValidationError
from ....vo import UserProfile, UserRole, UserState, UserSubscription


@dataclass(frozen=True)
class ChangeRole:
    old_role: UserRole
    new_role: UserRole

    def __post_init__(self) -> None:
        if not isinstance(self.old_role, UserRole):
            raise ValidationError("old_role must be a UserRole")
        if not isinstance(self.new_role, UserRole):
            raise ValidationError("new_role must be a UserRole")


@dataclass(frozen=True)
class ChangeSubscription:
    old_subscription: UserSubscription
    new_subscription: UserSubscription

    def __post_init__(self) -> None:
        if not isinstance(self.old_subscription, UserSubscription):
            raise ValidationError("old_subscription must be a UserSubscription")
        if not isinstance(self.new_subscription, UserSubscription):
            raise ValidationError("new_subscription must be a UserSubscription")


@dataclass(frozen=True)
class ChangeState:
    old_state: UserState
    new_state: UserState

    def __post_init__(self) -> None:
        if not isinstance(self.old_state, UserState):
            raise ValidationError("old_state must be a UserState")
        if not isinstance(self.new_state, UserState):
            raise ValidationError("new_state must be a UserState")


@dataclass(frozen=True)
class ChangeProfile:
    old_profile: UserProfile
    new_profile: UserProfile

    def __post_init__(self) -> None:
        if not isinstance(self.old_profile, UserProfile):
            raise ValidationError("old_profile must be a UserProfile")
        if not isinstance(self.new_profile, UserProfile):
            raise ValidationError("new_profile must be a UserProfile")


type ManagementAction = ChangeRole | ChangeSubscription | ChangeState | ChangeProfile

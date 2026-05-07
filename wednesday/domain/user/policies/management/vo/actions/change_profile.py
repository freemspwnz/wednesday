from dataclasses import dataclass

from .....vo import UserProfile
from .base import ManagementAction


@dataclass(frozen=True)
class ChangeProfile(ManagementAction):
    old_profile: UserProfile
    new_profile: UserProfile

    def __post_init__(self) -> None:
        UserProfile.ensure(self.old_profile)
        UserProfile.ensure(self.new_profile)

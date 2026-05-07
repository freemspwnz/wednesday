from dataclasses import dataclass

from .....vo import UserSubscription
from .base import ManagementAction


@dataclass(frozen=True)
class ChangeSubscription(ManagementAction):
    old_subscription: UserSubscription
    new_subscription: UserSubscription

    def __post_init__(self) -> None:
        UserSubscription.ensure(self.old_subscription)
        UserSubscription.ensure(self.new_subscription)

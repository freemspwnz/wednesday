from dataclasses import dataclass

from ..vo import UserSubscription
from .base import UserEvent


@dataclass(frozen=True)
class UserSubscriptionChanged(UserEvent):
    old_subscription: UserSubscription
    new_subscription: UserSubscription

    def __post_init__(self) -> None:
        super().__post_init__()

        UserSubscription.ensure(self.old_subscription)
        UserSubscription.ensure(self.new_subscription)


@dataclass(frozen=True)
class UserSubscriptionExpired(UserEvent):
    old_subscription: UserSubscription
    new_subscription: UserSubscription

    def __post_init__(self) -> None:
        super().__post_init__()

        UserSubscription.ensure(self.old_subscription)
        UserSubscription.ensure(self.new_subscription)

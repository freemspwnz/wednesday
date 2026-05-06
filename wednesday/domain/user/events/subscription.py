from dataclasses import dataclass

from ..exceptions import ValidationError
from ..vo import UserSubscription
from .base import UserEvent


@dataclass(frozen=True)
class UserSubscriptionChanged(UserEvent):
    old_subscription: UserSubscription
    new_subscription: UserSubscription

    def __post_init__(self) -> None:
        super().__post_init__()

        if not isinstance(self.old_subscription, UserSubscription):
            raise ValidationError("old_subscription must be a UserSubscription")

        if not isinstance(self.new_subscription, UserSubscription):
            raise ValidationError("new_subscription must be a UserSubscription")


@dataclass(frozen=True)
class UserSubscriptionExpired(UserEvent):
    old_subscription: UserSubscription
    new_subscription: UserSubscription

    def __post_init__(self) -> None:
        super().__post_init__()

        if not isinstance(self.old_subscription, UserSubscription):
            raise ValidationError("old_subscription must be a UserSubscription")

        if not isinstance(self.new_subscription, UserSubscription):
            raise ValidationError("new_subscription must be a UserSubscription")

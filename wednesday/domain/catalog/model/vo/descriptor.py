from dataclasses import dataclass
from typing import Self

from ....kernel import ValidationError
from ...subscription import SubscriptionTier
from .model import Model
from .series import Series
from .vendor import Vendor


@dataclass(frozen=True)
class ModelDescriptor:
    model: Model
    vendor: Vendor
    series: Series
    min_tier: SubscriptionTier
    display_name: str
    active: bool = True

    def __post_init__(self) -> None:
        Model.ensure(self.model)
        Vendor.ensure(self.vendor)
        Series.ensure(self.series)
        SubscriptionTier.ensure(self.min_tier)
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValidationError("display_name cannot be empty")
        if not isinstance(self.active, bool):
            raise ValidationError("active must be a bool")

    @classmethod
    def ensure(cls, descriptor: Self) -> Self:
        if not isinstance(descriptor, cls):
            raise ValidationError("descriptor must be a ModelDescriptor")
        return descriptor

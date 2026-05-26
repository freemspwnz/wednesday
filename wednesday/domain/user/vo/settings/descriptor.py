from dataclasses import dataclass
from typing import Self

from ...exceptions import ValidationError
from ..subscription import SubscriptionTier
from .model import Model
from .series import Series
from .vendor import Vendor


@dataclass(frozen=True)
class ModelDescriptor:
    model: Model
    vendor: Vendor
    series: Series
    display_name: str
    min_tier: SubscriptionTier
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValidationError("display_name cannot be empty")
        SubscriptionTier.ensure(self.min_tier)
        Model.ensure(self.model)
        Vendor.ensure(self.vendor)
        Series.ensure(self.series)

    @classmethod
    def ensure(cls, descriptor: Self) -> Self:
        if not isinstance(descriptor, cls):
            raise ValidationError("descriptor must be a ModelDescriptor")
        return descriptor

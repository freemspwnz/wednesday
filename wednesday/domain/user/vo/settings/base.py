from dataclasses import dataclass
from typing import Self

from ...exceptions import ValidationError
from .descriptor import ModelDescriptor
from .model import Model
from .series import Series
from .vendor import Vendor


@dataclass(frozen=True)
class UserSettings:
    vendor: Vendor
    series: Series
    model: Model

    def __post_init__(self) -> None:
        Vendor.ensure(self.vendor)
        Series.ensure(self.series)
        Model.ensure(self.model)

    @classmethod
    def ensure(cls, settings: Self) -> Self:
        if not isinstance(settings, cls):
            raise ValidationError("settings must be a UserSettings")
        return settings

    @classmethod
    def from_descriptor(cls, descriptor: ModelDescriptor) -> Self:
        return cls(
            vendor=descriptor.vendor,
            series=descriptor.series,
            model=descriptor.model,
        )

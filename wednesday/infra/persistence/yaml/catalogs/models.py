from dataclasses import dataclass, field

from domain.catalog import Model, ModelCatalog, ModelDescriptor, Series, SubscriptionTier, Vendor
from domain.kernel.exceptions import ValidationError


@dataclass(slots=True)
class YamlModelCatalog(ModelCatalog):
    """Read-only in-memory ModelCatalog snapshot."""

    _by_model: dict[str, ModelDescriptor] = field(default_factory=dict)
    _ordered: list[ModelDescriptor] = field(default_factory=list)
    _vendors: list[Vendor] = field(default_factory=list)
    _series_by_vendor: dict[str, list[Series]] = field(default_factory=dict)
    _models_by_vendor_series: dict[tuple[str, str], list[Model]] = field(default_factory=dict)

    async def get_by_model(self, model: Model) -> ModelDescriptor | None:
        return self._by_model.get(str(Model.ensure(model)))

    async def default_for_tier(self, tier: SubscriptionTier) -> ModelDescriptor:
        tier = SubscriptionTier.ensure(tier)
        candidates = [item for item in self._ordered if item.active and item.min_tier <= tier]
        if not candidates:
            raise ValidationError(f"no active model for tier {tier.name}")

        best_tier = max(item.min_tier for item in candidates)
        for item in candidates:
            if item.min_tier == best_tier:
                return item
        raise ValidationError(f"no active model for tier {tier.name}")

    async def exists(self, model: Model) -> bool:
        return str(Model.ensure(model)) in self._by_model

    async def list_active(self) -> list[ModelDescriptor]:
        return sorted(
            [item for item in self._by_model.values() if item.active],
            key=lambda item: str(item.model),
        )

    async def list_vendors(self) -> list[Vendor]:
        return list(self._vendors)

    async def list_series(self, vendor: Vendor) -> list[Series]:
        vendor = Vendor.ensure(vendor)
        return list(self._series_by_vendor.get(str(vendor), []))

    async def list_models(self, vendor: Vendor, series: Series) -> list[Model]:
        vendor = Vendor.ensure(vendor)
        series = Series.ensure(series)
        return list(self._models_by_vendor_series.get((str(vendor), str(series)), []))

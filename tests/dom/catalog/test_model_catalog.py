from dataclasses import dataclass

import pytest

from domain.catalog import Model, ModelCatalog, ModelDescriptor, Series, SubscriptionTier, Vendor
from domain.kernel import ValidationError


def _descriptor(*, model: str, min_tier: SubscriptionTier, active: bool = True) -> ModelDescriptor:
    return ModelDescriptor(
        model=Model.parse(model),
        vendor=Vendor.parse("sber"),
        series=Series.parse("gigachat"),
        min_tier=min_tier,
        display_name=model,
        active=active,
    )


@dataclass
class _FakeModelCatalog(ModelCatalog):
    entries: dict[str, ModelDescriptor]

    async def get_by_model(self, model: Model) -> ModelDescriptor | None:
        return self.entries.get(str(model))

    async def default_for_tier(self, tier: SubscriptionTier) -> ModelDescriptor:
        return self.entries["gigachat-2-pro"] if tier is SubscriptionTier.PREMIUM else self.entries["gigachat-2-lite"]

    async def exists(self, model: Model) -> bool:
        return str(model) in self.entries

    async def list_active(self) -> list[ModelDescriptor]:
        return [item for item in self.entries.values() if item.active]

    async def list_vendors(self) -> list[Vendor]:
        return [Vendor.parse("sber")]

    async def list_series(self, vendor: Vendor) -> list[Series]:
        _ = Vendor.ensure(vendor)
        return [Series.parse("gigachat")]

    async def list_models(self, vendor: Vendor, series: Series) -> list[Model]:
        _ = Vendor.ensure(vendor)
        _ = Series.ensure(series)
        return [item.model for item in self.entries.values()]


@pytest.mark.unit
def test_model_vo_parse_and_validation() -> None:
    assert str(Model.parse(" GigaChat-2-Lite ")) == "gigachat-2-lite"
    assert str(Vendor.parse("SBER")) == "sber"
    assert str(Series.parse("GigaChat")) == "gigachat"

    with pytest.raises(ValidationError):
        Model.parse("bad slug")
    with pytest.raises(ValidationError):
        Vendor.parse("")
    with pytest.raises(ValidationError):
        Series.parse("x" * 65)


@pytest.mark.unit
def test_model_descriptor_validates_required_fields() -> None:
    descriptor = _descriptor(model="gigachat-2-lite", min_tier=SubscriptionTier.FREE)
    assert descriptor.active

    with pytest.raises(ValidationError):
        ModelDescriptor(
            model=Model.parse("gigachat-2-lite"),
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            min_tier=SubscriptionTier.FREE,
            display_name=" ",
        )
    with pytest.raises(ValidationError):
        ModelDescriptor(
            model=Model.parse("gigachat-2-lite"),
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            min_tier=SubscriptionTier.FREE,
            display_name="Lite",
            active="yes",  # type: ignore[arg-type]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_catalog_protocol_shape_and_ensure() -> None:
    catalog = _FakeModelCatalog(
        entries={
            "gigachat-2-lite": _descriptor(model="gigachat-2-lite", min_tier=SubscriptionTier.FREE),
            "gigachat-2-pro": _descriptor(model="gigachat-2-pro", min_tier=SubscriptionTier.PREMIUM),
        }
    )
    ensured = ModelCatalog.ensure(catalog)
    assert ensured is catalog
    assert await catalog.exists(Model.parse("gigachat-2-lite"))
    assert len(await catalog.list_active()) == 2
    assert (await catalog.default_for_tier(SubscriptionTier.PREMIUM)).model == Model.parse("gigachat-2-pro")

    with pytest.raises(ValidationError):
        ModelCatalog.ensure("bad")  # type: ignore[arg-type]

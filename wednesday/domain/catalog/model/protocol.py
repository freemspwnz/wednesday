from typing import Protocol, Self, runtime_checkable

from ...kernel.exceptions import ValidationError
from ..subscription import SubscriptionTier
from .vo import Model, ModelDescriptor, Series, Vendor


@runtime_checkable
class ModelCatalog(Protocol):
    """Read-only registry of image generation models (vendor / series / model)."""

    async def get_by_model(self, model: Model) -> ModelDescriptor | None:
        """Get model descriptor by model."""
        ...

    async def default_for_tier(self, tier: SubscriptionTier) -> ModelDescriptor:
        """Default descriptor for tier."""
        ...

    async def exists(self, model: Model) -> bool:
        """Check if model exists."""
        ...

    async def list_active(self) -> list[ModelDescriptor]:
        """All active model descriptors."""
        ...

    async def list_vendors(self) -> list[Vendor]:
        """List vendors."""
        ...

    async def list_series(self, vendor: Vendor) -> list[Series]:
        """List series by vendor."""
        ...

    async def list_models(self, vendor: Vendor, series: Series) -> list[Model]:
        """List models by vendor and series."""
        ...

    @classmethod
    def ensure(cls, catalog: Self) -> Self:
        if not isinstance(catalog, cls):
            raise ValidationError("catalog must be a ModelCatalog")
        return catalog

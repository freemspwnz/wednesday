from typing import Protocol, Self, runtime_checkable

from ...kernel.exceptions import ValidationError
from .vo import SubscriptionPlan, SubscriptionTier


@runtime_checkable
class SubscriptionCatalog(Protocol):
    """Read-only registry of subscription plans."""

    async def get_by_tier(self, tier: SubscriptionTier) -> SubscriptionPlan:
        """Get subscription plan by tier."""
        ...

    async def list_active(self) -> list[SubscriptionPlan]:
        """All active subscription plans."""
        ...

    async def default_plan(self) -> SubscriptionPlan:
        """Default plan for new users."""
        ...

    @classmethod
    def ensure(cls, catalog: Self) -> Self:
        if not isinstance(catalog, cls):
            raise ValidationError("catalog must be a SubscriptionCatalog")
        return catalog

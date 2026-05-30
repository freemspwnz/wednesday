from __future__ import annotations

from dataclasses import dataclass, field

from domain.catalog import SubscriptionCatalog, SubscriptionPlan, SubscriptionTier
from domain.kernel.exceptions import ValidationError


@dataclass(slots=True)
class YamlSubscriptionCatalog(SubscriptionCatalog):
    """Read-only in-memory SubscriptionCatalog snapshot."""

    _plans: dict[SubscriptionTier, SubscriptionPlan] = field(default_factory=dict)

    async def get_by_tier(self, tier: SubscriptionTier) -> SubscriptionPlan:
        tier = SubscriptionTier.ensure(tier)
        plan = self._plans.get(tier)
        if plan is None:
            raise ValidationError(f"subscription plan not found for tier {tier.name}")
        return plan

    async def list_active(self) -> list[SubscriptionPlan]:
        return [self._plans[tier] for tier in sorted(self._plans, key=lambda item: item.value)]

    async def default_plan(self) -> SubscriptionPlan:
        return self._plans[SubscriptionTier.FREE]

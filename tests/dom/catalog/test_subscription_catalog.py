from __future__ import annotations

from dataclasses import dataclass

import pytest

from domain.catalog import SubscriptionCatalog, SubscriptionPlan, SubscriptionTier
from domain.kernel import ValidationError

from . import FREE_PLAN, PREMIUM_PLAN


@dataclass
class _FakeSubscriptionCatalog(SubscriptionCatalog):
    plans: dict[SubscriptionTier, SubscriptionPlan]

    async def get_by_tier(self, tier: SubscriptionTier) -> SubscriptionPlan:
        return self.plans[tier]

    async def list_active(self) -> list[SubscriptionPlan]:
        return list(self.plans.values())

    async def default_plan(self) -> SubscriptionPlan:
        return self.plans[SubscriptionTier.FREE]


@pytest.mark.unit
def test_subscription_tier_and_plan_helpers() -> None:
    free = FREE_PLAN
    premium = PREMIUM_PLAN
    assert free.tier is SubscriptionTier.FREE
    assert premium.tier is SubscriptionTier.PREMIUM
    assert free.daily_limit < premium.daily_limit

    with pytest.raises(ValidationError):
        SubscriptionPlan(tier="free", daily_limit=1, cooldown_minutes=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SubscriptionPlan(tier=SubscriptionTier.FREE, daily_limit=0, cooldown_minutes=0)
    with pytest.raises(ValidationError):
        SubscriptionPlan(tier=SubscriptionTier.FREE, daily_limit=1, cooldown_minutes=-1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscription_catalog_protocol_shape_and_ensure() -> None:
    catalog = _FakeSubscriptionCatalog(
        plans={
            SubscriptionTier.FREE: FREE_PLAN,
            SubscriptionTier.PREMIUM: PREMIUM_PLAN,
        }
    )
    ensured = SubscriptionCatalog.ensure(catalog)
    assert ensured is catalog
    assert (await catalog.get_by_tier(SubscriptionTier.FREE)).tier is SubscriptionTier.FREE
    assert len(await catalog.list_active()) == 2
    assert (await catalog.default_plan()).tier is SubscriptionTier.FREE

    with pytest.raises(ValidationError):
        SubscriptionCatalog.ensure("bad")  # type: ignore[arg-type]

from ...vo import AwareDatetime, ModelDescriptor, UserSubscription
from .vo import (
    ModelSelectionAllowed,
    ModelSelectionCode,
    ModelSelectionDecision,
    ModelSelectionDenied,
)


class ModelSelectionPolicy:
    """Policy for selecting a model for a user."""

    @classmethod
    def evaluate(
        cls,
        subscription: UserSubscription,
        descriptor: ModelDescriptor,
        at: AwareDatetime,
    ) -> ModelSelectionDecision:
        effective = subscription.effective_at(at)
        if not descriptor.active:
            return cls.deny(ModelSelectionCode.MODEL_NOT_ACTIVE)
        if effective.plan.tier < descriptor.min_tier:
            return cls.deny(ModelSelectionCode.TIER_TOO_LOW)
        return cls.allow()

    @classmethod
    def allow(cls) -> ModelSelectionAllowed:
        return ModelSelectionAllowed()

    @classmethod
    def deny(cls, code: ModelSelectionCode) -> ModelSelectionDenied:
        return ModelSelectionDenied(code)

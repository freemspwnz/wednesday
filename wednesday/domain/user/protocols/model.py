from typing import Protocol, Self, runtime_checkable

from ..exceptions import ValidationError
from ..vo import Model, ModelDescriptor, SubscriptionTier


@runtime_checkable
class ModelRepo(Protocol):
    """Read-only registry of image generation models (vendor / series / model)."""

    async def get_by_model(self, model: Model) -> ModelDescriptor | None:
        """Get model descriptor by model."""
        ...

    async def list_active(self) -> list[ModelDescriptor]:
        """All active model descriptors."""
        ...

    async def default_for_tier(self, tier: SubscriptionTier) -> Model:
        """Default model for tier."""
        ...

    @classmethod
    def ensure(cls, registry: Self) -> Self:
        if not isinstance(registry, cls):
            raise ValidationError("registry must be a ModelRepo")
        return registry

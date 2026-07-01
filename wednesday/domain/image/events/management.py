from dataclasses import dataclass

from domain.user import UserRole

from .base import ImageEvent


@dataclass(frozen=True)
class ImageHidden(ImageEvent):
    """Catalog image was hidden."""

    actor: UserRole

    def __post_init__(self) -> None:
        super().__post_init__()
        UserRole.ensure(self.actor)


@dataclass(frozen=True)
class ImageShown(ImageEvent):
    """Catalog image was shown."""

    actor: UserRole

    def __post_init__(self) -> None:
        super().__post_init__()
        UserRole.ensure(self.actor)

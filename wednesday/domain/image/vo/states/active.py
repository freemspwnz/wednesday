from dataclasses import dataclass

from .base import ImageStatus


@dataclass(frozen=True)
class ActiveStatus(ImageStatus):
    """Image is visible for /random and generate fallback."""

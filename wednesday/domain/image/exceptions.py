from ..kernel.exceptions import (
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)


class ImageError(DomainError):
    """Errors from the image bounded context."""


class ImageNotFoundError(ImageError):
    """Catalog image not found."""

    def __init__(self, image_id: str) -> None:
        self.image_id = image_id
        super().__init__(f"image not found: {image_id}")


__all__ = [
    "ImageError",
    "ImageNotFoundError",
    "InvalidStateTransitionError",
    "StaleWriteError",
    "ValidationError",
]

from ..kernel.exceptions import AccessDeniedError, DomainError, ValidationError


class ImageError(DomainError):
    """Errors from the image bounded context."""


class ImageNotFoundError(ImageError):
    """Catalog image not found."""

    def __init__(self, image_id: str) -> None:
        self.image_id = image_id
        super().__init__(f"image not found: {image_id}")


class PromptRejectedError(ImageError):
    """User prompt rejected by moderation policy."""

    def __init__(self, code: str, meta: dict[str, str] | None = None) -> None:
        if not isinstance(code, str) or not code:
            raise ValidationError("code must be a non-empty str")
        resolved_meta = meta or {}
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in resolved_meta.items()):
            raise ValidationError("meta keys and values must be strings")
        self.code = code
        self.meta = resolved_meta
        super().__init__(f"prompt rejected: {code}")


class TextGenError(ImageError):
    """Text generator error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


__all__ = [
    "AccessDeniedError",
    "ImageError",
    "ImageNotFoundError",
    "PromptRejectedError",
    "TextGenError",
    "ValidationError",
]

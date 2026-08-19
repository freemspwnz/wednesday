from ..base import AppError


class UnknownProviderError(AppError):
    """Unknown provider error."""

    def __init__(self, vendor: str) -> None:
        super().__init__(f"no generator registered for vendor: {vendor}")
        self.vendor = vendor

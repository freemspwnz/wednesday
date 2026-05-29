from dataclasses import dataclass

from .base import ImageStatus
from .reason import HiddenReason


@dataclass(frozen=True)
class HiddenStatus(ImageStatus):
    reason: HiddenReason

    def __post_init__(self) -> None:
        HiddenReason.ensure(self.reason)

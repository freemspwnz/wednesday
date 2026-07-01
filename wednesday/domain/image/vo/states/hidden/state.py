from dataclasses import dataclass

from ..base import ImageState
from .reason import HiddenReason


@dataclass(frozen=True)
class HiddenState(ImageState):
    reason: HiddenReason

    def __post_init__(self) -> None:
        HiddenReason.ensure(self.reason)

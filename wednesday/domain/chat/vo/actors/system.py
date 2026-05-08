from dataclasses import dataclass

from .base import ManagementActor


@dataclass(frozen=True)
class System(ManagementActor):
    """System actor."""

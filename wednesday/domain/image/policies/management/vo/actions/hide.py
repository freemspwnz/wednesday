from dataclasses import dataclass

from .base import ManagementAction


@dataclass(frozen=True)
class HideImage(ManagementAction):
    """Admin action to hide a catalog image."""

from dataclasses import dataclass

from .base import ManagementAction


@dataclass(frozen=True)
class ShowImage(ManagementAction):
    """Admin action to show a catalog image hidden by an admin."""

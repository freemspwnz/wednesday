from dataclasses import dataclass

from .....vo import UserState
from .base import ManagementAction


@dataclass(frozen=True)
class Unban(ManagementAction):
    old_state: UserState

    def __post_init__(self) -> None:
        UserState.ensure(self.old_state)

from dataclasses import dataclass

from .....vo import AwareDatetime, UserState
from .base import ManagementAction


@dataclass(frozen=True)
class Ban(ManagementAction):
    old_state: UserState
    until: AwareDatetime

    def __post_init__(self) -> None:
        UserState.ensure(self.old_state)
        AwareDatetime.ensure(self.until)

from typing import Protocol, runtime_checkable

from ....kernel.vo import AwareDatetime


@runtime_checkable
class UserState(Protocol):
    def is_banned_at(self, now: AwareDatetime) -> bool: ...

    def ban_until(self, until: AwareDatetime, now: AwareDatetime) -> "UserState": ...

    def unban(self) -> "UserState": ...

    def refresh(self, now: AwareDatetime) -> "UserState": ...

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ....kernel.vo import AwareDatetime


@runtime_checkable
class UserState(Protocol):
    def is_banned_at(self, now: AwareDatetime) -> bool: ...

    def ban_until(self, until: AwareDatetime, now: AwareDatetime) -> UserState: ...

    def unban(self) -> UserState: ...

    def effective_at(self, now: AwareDatetime, fallback: UserState) -> UserState: ...

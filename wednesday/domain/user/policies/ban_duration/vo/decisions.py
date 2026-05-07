from dataclasses import dataclass

from ....vo import AwareDatetime
from .code import BanDurationCode


@dataclass(frozen=True)
class BanAssigned:
    banned_until: AwareDatetime
    code: BanDurationCode

    def __post_init__(self) -> None:
        AwareDatetime.ensure(self.banned_until)
        BanDurationCode.ensure(self.code)


@dataclass(frozen=True)
class NoBan:
    pass


type BanDurationDecision = BanAssigned | NoBan

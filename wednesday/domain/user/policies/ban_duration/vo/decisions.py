from dataclasses import dataclass

from ....exceptions import ValidationError
from ....vo import AwareDatetime
from .code import BanDurationCode


@dataclass(frozen=True)
class BanAssigned:
    banned_until: AwareDatetime
    code: BanDurationCode

    def __post_init__(self) -> None:
        if not isinstance(self.banned_until, AwareDatetime):
            raise ValidationError("banned_until must be a AwareDatetime")

        if not isinstance(self.code, BanDurationCode):
            raise ValidationError("code must be a BanDurationCode")


@dataclass(frozen=True)
class NoBan:
    pass


type BanDurationDecision = BanAssigned | NoBan

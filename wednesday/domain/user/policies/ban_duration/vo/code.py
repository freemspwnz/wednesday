from enum import IntEnum
from typing import Self

from ....exceptions import ValidationError


class BanDurationCode(IntEnum):
    BAN_1_HOUR = 1
    BAN_1_DAY = 2
    BAN_1_WEEK = 3
    BAN_1_YEAR = 4

    @classmethod
    def ensure(cls, code: object) -> Self:
        if not isinstance(code, cls):
            raise ValidationError(f"Code must be an instance of {cls.__name__}")
        return code

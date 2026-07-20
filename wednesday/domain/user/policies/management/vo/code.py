from enum import StrEnum
from typing import Self

from ....exceptions import ValidationError


class ManagementAccessCode(StrEnum):
    ACCESS_DENIED = "access_denied"

    @classmethod
    def ensure(cls, code: Self) -> Self:
        if not isinstance(code, cls):
            raise ValidationError("code must be a ManagementAccessCode")
        return code

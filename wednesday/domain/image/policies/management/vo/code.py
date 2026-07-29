from enum import StrEnum
from typing import Self

from ....exceptions import ValidationError


class ManagementAccessCode(StrEnum):
    ACCESS_DENIED = "access_denied"

    @classmethod
    def ensure(cls, code: object) -> Self:
        if not isinstance(code, cls):
            raise ValidationError(f"code must be a {cls.__name__}")
        return code

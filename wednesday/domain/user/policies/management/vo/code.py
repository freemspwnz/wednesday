from enum import StrEnum
from typing import Self

from ....exceptions import ValidationError


class ManagementAccessCode(StrEnum):
    ACCESS_DENIED = "access_denied"

    @classmethod
    def ensure(cls, code: object) -> Self:
        if not isinstance(code, cls):
            raise ValidationError(f"Code must be an instance of {cls.__name__}")
        return code

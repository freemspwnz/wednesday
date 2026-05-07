from __future__ import annotations

from enum import StrEnum

from ....exceptions import ValidationError


class ManagementAccessCode(StrEnum):
    ACCESS_DENIED = "access_denied"

    @classmethod
    def ensure(cls, code: ManagementAccessCode) -> ManagementAccessCode:
        if not isinstance(code, cls):
            raise ValidationError("code must be a ManagementAccessCode")
        return code

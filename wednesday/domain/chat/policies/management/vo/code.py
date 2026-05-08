from __future__ import annotations

from enum import StrEnum

from ....exceptions import ValidationError


class ManagementAccessCode(StrEnum):
    NOT_ENOUGH_RIGHTS = "not_enough_rights"
    UNKNOWN_ACTOR = "unknown_actor"
    ACTOR_CHAT_MISMATCH = "actor_chat_mismatch"

    @classmethod
    def ensure(cls, code: ManagementAccessCode) -> ManagementAccessCode:
        if not isinstance(code, cls):
            raise ValidationError("code must be a ManagementAccessCode")
        return code

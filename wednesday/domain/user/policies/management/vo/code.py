from enum import StrEnum


class ManagementAccessCode(StrEnum):
    ACCESS_DENIED = "access_denied"
    TARGET_UNMANAGEABLE = "target_unmanageable"
    NOT_ENOUGH_RIGHTS = "not_enough_rights"
    NO_EFFECT = "no_effect"
    INVALID_CONTEXT = "invalid_context"
    INVALID_ACTION = "invalid_action"

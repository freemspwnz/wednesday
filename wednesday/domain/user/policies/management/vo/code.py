from enum import StrEnum


class ManagementAccessCode(StrEnum):
    NOT_ENOUGH_RIGHTS = "not_enough_rights"
    TARGET_UNMANAGEABLE = "target_unmanageable"

from enum import StrEnum


class LimitViolationCode(StrEnum):
    COOLDOWN = "cooldown"
    DAILY_LIMIT = "daily_limit"

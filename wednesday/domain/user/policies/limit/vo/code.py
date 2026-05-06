from enum import StrEnum


class LimitViolationCode(StrEnum):
    COOLDOWN = "cooldown"
    DAILY_LIMIT_EXCEEDED = "daily_limit_exceeded"

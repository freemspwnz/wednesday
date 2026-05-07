from ...vo import AwareDatetime
from .vo import (
    BanAssigned,
    BanDuration,
    BanDurationCode,
    BanDurationDecision,
    NoBan,
    ViolationStats,
)

MAX_TOTAL_VIOLATIONS = 10
MAX_WEEKLY_VIOLATIONS = 5
MAX_DAILY_VIOLATIONS = 3
MAX_HOURLY_VIOLATIONS = 2


class BanDurationPolicy:
    """
    Advanced domain policy for moderation.
    """

    @classmethod
    def evaluate(
        cls,
        stats: ViolationStats,
        at: AwareDatetime,
    ) -> BanDurationDecision:
        if stats.total >= MAX_TOTAL_VIOLATIONS:
            return cls.assign(at + BanDuration.year(), BanDurationCode.BAN_1_YEAR)

        if stats.week >= MAX_WEEKLY_VIOLATIONS:
            return cls.assign(at + BanDuration.week(), BanDurationCode.BAN_1_WEEK)

        if stats.today >= MAX_DAILY_VIOLATIONS:
            return cls.assign(at + BanDuration.day(), BanDurationCode.BAN_1_DAY)

        if stats.hour >= MAX_HOURLY_VIOLATIONS:
            return cls.assign(at + BanDuration.hour(), BanDurationCode.BAN_1_HOUR)

        return cls.deny()

    @classmethod
    def assign(
        cls,
        banned_until: AwareDatetime,
        code: BanDurationCode,
    ) -> BanAssigned:
        return BanAssigned(
            banned_until=banned_until,
            code=code,
        )

    @classmethod
    def deny(cls) -> NoBan:
        return NoBan()

from typing import ClassVar

from ...vo import AwareDatetime
from .vo import (
    BanAssigned,
    BanDuration,
    BanDurationCode,
    BanDurationDecision,
    NoBan,
    ViolationStats,
)


class BanDurationPolicy:
    """
    Advanced domain policy for moderation.
    """

    _MAX_TOTAL_VIOLATIONS: ClassVar[int] = 10
    _MAX_WEEKLY_VIOLATIONS: ClassVar[int] = 5
    _MAX_DAILY_VIOLATIONS: ClassVar[int] = 3
    _MAX_HOURLY_VIOLATIONS: ClassVar[int] = 2

    @classmethod
    def evaluate(
        cls,
        stats: ViolationStats,
        at: AwareDatetime,
    ) -> BanDurationDecision:
        if stats.total >= cls._MAX_TOTAL_VIOLATIONS:
            return cls.assign(at + BanDuration.year(), BanDurationCode.BAN_1_YEAR)

        if stats.week >= cls._MAX_WEEKLY_VIOLATIONS:
            return cls.assign(at + BanDuration.week(), BanDurationCode.BAN_1_WEEK)

        if stats.today >= cls._MAX_DAILY_VIOLATIONS:
            return cls.assign(at + BanDuration.day(), BanDurationCode.BAN_1_DAY)

        if stats.hour >= cls._MAX_HOURLY_VIOLATIONS:
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

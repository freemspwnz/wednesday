from dataclasses import dataclass
from typing import ClassVar, Self

from ...kernel.vo import NonEmptyStr
from ..exceptions import ValidationError


@dataclass(frozen=True)
class UserProfile:
    """Value Object: user profile."""

    _MAX_USERNAME_LENGTH: ClassVar[int] = 64

    telegram_id: int
    is_bot: bool
    first_name: NonEmptyStr
    last_name: NonEmptyStr | None = None
    username: str | None = None
    language_code: str | None = None
    has_tg_premium: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.telegram_id, int):
            raise ValidationError("telegram_id must be int")
        if self.telegram_id <= 0:
            raise ValidationError("telegram_id must be positive")
        if self.username and len(self.username) > self._MAX_USERNAME_LENGTH:
            raise ValidationError("username too long")

    @property
    def full_name(self) -> NonEmptyStr:
        parts = [str(p) for p in (self.first_name, self.last_name) if p and str(p).strip()]
        return NonEmptyStr(" ".join(parts))

    @classmethod
    def ensure(cls, profile: object) -> Self:
        if not isinstance(profile, cls):
            raise ValidationError(f"Profile must be an instance of {cls.__name__}")
        return profile

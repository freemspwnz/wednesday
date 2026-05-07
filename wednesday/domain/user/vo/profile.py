from __future__ import annotations

from dataclasses import dataclass

from ...kernel.vo import NonEmptyStr
from ..exceptions import ValidationError

MAX_USERNAME_LENGTH = 64


@dataclass(frozen=True)
class UserProfile:
    telegram_id: int
    is_bot: bool
    first_name: NonEmptyStr
    last_name: NonEmptyStr | None = None
    username: str | None = None
    language_code: str | None = None
    has_tg_premium: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.telegram_id, int):
            raise ValidationError("telegram_id must be int")
        if self.telegram_id <= 0:
            raise ValidationError("telegram_id must be positive")
        if self.username and len(self.username) > MAX_USERNAME_LENGTH:
            raise ValidationError("username too long")

    @classmethod
    def ensure(cls, profile: UserProfile) -> UserProfile:
        if not isinstance(profile, UserProfile):
            raise ValidationError("profile must be a UserProfile")
        return profile

    @property
    def full_name(self) -> NonEmptyStr:
        parts = [str(p) for p in (self.first_name, self.last_name) if p and str(p).strip()]
        return NonEmptyStr(" ".join(parts))

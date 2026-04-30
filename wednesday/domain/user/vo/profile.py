from dataclasses import dataclass

from ...kernel.vo import NonEmptyStr
from ..exceptions import ValidationError

MAX_USERNAME_LENGTH = 64


@dataclass(frozen=True)
class UserProfile:
    is_bot: bool
    first_name: NonEmptyStr
    last_name: NonEmptyStr | None = None
    username: str | None = None
    language_code: str | None = None
    has_tg_premium: bool = False

    def __post_init__(self) -> None:
        if self.username and len(self.username) > MAX_USERNAME_LENGTH:
            raise ValidationError("username too long")

    @property
    def full_name(self) -> NonEmptyStr:
        parts = [str(p) for p in (self.first_name, self.last_name) if p and str(p).strip()]
        return NonEmptyStr(" ".join(parts))

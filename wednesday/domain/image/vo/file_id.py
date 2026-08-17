from dataclasses import dataclass
from typing import ClassVar, Self

from ..exceptions import ValidationError


@dataclass(frozen=True)
class TelegramFileId:
    """Value Object: telegram file id."""

    _MAX_LENGTH: ClassVar[int] = 256

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValidationError("value must be a str")
        if not self.value.strip():
            raise ValidationError("telegram file id cannot be empty")
        if len(self.value) > self._MAX_LENGTH:
            raise ValidationError(f"telegram file id exceeds max length {self._MAX_LENGTH}")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, raw: str) -> Self:
        if not isinstance(raw, str):
            raise ValidationError("value must be a str")
        return cls(value=raw.strip())

    @classmethod
    def ensure(cls, file_id: object) -> Self:
        if not isinstance(file_id, cls):
            raise ValidationError(f"file_id must be an instance of {cls.__name__}")
        return file_id

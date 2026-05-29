from dataclasses import dataclass
from typing import Self

from ..exceptions import ValidationError

_MAX_LENGTH = 256


@dataclass(frozen=True)
class TelegramFileId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValidationError("value must be a str")
        if not self.value.strip():
            raise ValidationError("telegram file id cannot be empty")
        if len(self.value) > _MAX_LENGTH:
            raise ValidationError(f"telegram file id exceeds max length {_MAX_LENGTH}")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, raw: str) -> Self:
        if not isinstance(raw, str):
            raise ValidationError("value must be a str")
        return cls(value=raw.strip())

    @classmethod
    def ensure(cls, file_id: Self) -> Self:
        if not isinstance(file_id, TelegramFileId):
            raise ValidationError("file_id must be a TelegramFileId")
        return file_id

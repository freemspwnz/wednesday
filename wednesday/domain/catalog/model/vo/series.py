import re
from dataclasses import dataclass
from typing import Self

from ....kernel import ValidationError

_MAX_CODE_LENGTH = 64
_CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Series:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValidationError("series must be a str")
        if not self.value:
            raise ValidationError("series cannot be empty")
        if len(self.value) > _MAX_CODE_LENGTH:
            raise ValidationError(f"series exceeds max length {_MAX_CODE_LENGTH}")
        if not _CODE_PATTERN.match(self.value):
            raise ValidationError("series must contain only lowercase letters, digits and hyphens")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, raw: str) -> Self:
        if not isinstance(raw, str):
            raise ValidationError("series must be a str")
        return cls(value=raw.strip().lower())

    @classmethod
    def ensure(cls, series: Self) -> Self:
        if not isinstance(series, Series):
            raise ValidationError("series must be a Series")
        return series

import re
from dataclasses import dataclass
from typing import ClassVar, Self

from ....kernel import ValidationError


@dataclass(frozen=True)
class Vendor:
    """Value Object: vendor."""

    _MAX_CODE_LENGTH: ClassVar[int] = 64
    _CODE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValidationError("vendor must be a str")
        if not self.value:
            raise ValidationError("vendor cannot be empty")
        if len(self.value) > self._MAX_CODE_LENGTH:
            raise ValidationError(f"vendor exceeds max length {self._MAX_CODE_LENGTH}")
        if not self._CODE_PATTERN.match(self.value):
            raise ValidationError("vendor must contain only lowercase letters, digits and hyphens")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, raw: str) -> Self:
        if not isinstance(raw, str):
            raise ValidationError("vendor must be a str")
        return cls(value=raw.strip().lower())

    @classmethod
    def ensure(cls, vendor: object) -> Self:
        if not isinstance(vendor, cls):
            raise ValidationError(f"vendor must be an instance of {cls.__name__}")
        return vendor

from dataclasses import dataclass
from typing import ClassVar, Self

from ...exceptions import ValidationError


@dataclass(frozen=True)
class NormalizedPrompt:
    value: str
    _MAX_LENGTH: ClassVar[int] = 1000

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValidationError("prompt must be a str")
        if not self.value:
            raise ValidationError("prompt cannot be empty")
        if len(self.value) > self._MAX_LENGTH:
            raise ValidationError(f"prompt exceeds max length {self._MAX_LENGTH}")
        if self.value != self._normalize(self.value):
            raise ValidationError("prompt must be normalized; use NormalizedPrompt.parse")

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.strip().split())

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, raw: str) -> Self:
        if not isinstance(raw, str):
            raise ValidationError("prompt must be a str")
        return cls(value=cls._normalize(raw))

    @classmethod
    def ensure(cls, prompt: object) -> Self:
        if not isinstance(prompt, cls):
            raise ValidationError(f"prompt must be an instance of {cls.__name__}")
        return prompt

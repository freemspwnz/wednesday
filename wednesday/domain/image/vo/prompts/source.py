from enum import StrEnum
from typing import Self

from ...exceptions import ValidationError


class PromptSource(StrEnum):
    USER = "user"
    FALLBACK = "fallback"
    LLM = "llm"

    @classmethod
    def ensure(cls, source: object) -> Self:
        if not isinstance(source, cls):
            raise ValidationError(f"source must be an instance of {cls.__name__}")
        return source

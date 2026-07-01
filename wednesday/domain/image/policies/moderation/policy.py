from __future__ import annotations

import re
from collections.abc import Sequence

from ...exceptions import ValidationError
from .vo import (
    ModerationAllowed,
    ModerationCode,
    ModerationDecision,
    ModerationDenied,
    ModerationViolation,
)


class PromptModerationPolicy:
    DEFAULT_BANNED_WORDS: tuple[str, ...] = ("porn", "naked", "blood")

    def __init__(self, banned_words: Sequence[str] | None = None) -> None:
        source = banned_words or self.DEFAULT_BANNED_WORDS
        normalized = tuple(dict.fromkeys(w.strip().lower() for w in source if w and w.strip()))
        if not normalized:
            raise ValidationError("banned_words cannot be empty after normalization")
        self._banned_words = normalized

    def evaluate(self, text: str) -> ModerationDecision:
        if not text or not text.strip():
            return self.allow()

        lowered = text.lower()
        for word in self._banned_words:
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                return self.deny(code=ModerationCode.PROHIBITED_CONTENT, meta={"word": word})
        return self.allow()

    @classmethod
    def allow(cls) -> ModerationAllowed:
        return ModerationAllowed()

    @classmethod
    def deny(cls, code: ModerationCode, meta: dict[str, str]) -> ModerationDenied:
        return ModerationDenied(
            violation=ModerationViolation(
                code=code,
                meta=meta,
            )
        )

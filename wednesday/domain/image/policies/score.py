from collections.abc import Sequence

from domain.user import UserRole

from ..exceptions import ValidationError


class ImageScorePolicy:
    """Catalog image score: base 3 plus vote sum; hidden at or below zero."""

    BASE: int = 3
    # Repo filter uses score > min_score - 1; keep aligned with is_selectable (score > 0).
    CATALOG_MIN_SCORE: int = 1
    _VOTE_VALUES = frozenset({-1, 1})

    @classmethod
    def compute(cls, vote_values: Sequence[int]) -> int:
        for value in vote_values:
            if value not in cls._VOTE_VALUES:
                raise ValidationError("vote value must be -1 or 1")
        return cls.BASE + sum(vote_values)

    @classmethod
    def on_show(cls, actor: UserRole, current_score: int) -> int:
        match actor:
            case UserRole.SYSTEM:
                return current_score
            case UserRole.OWNER:
                return cls.BASE
            case _:
                raise ValidationError("unknown actor")

    @classmethod
    def is_hidden(cls, score: int) -> bool:
        return score <= 0

    @classmethod
    def is_selectable(cls, score: int) -> bool:
        return score > 0

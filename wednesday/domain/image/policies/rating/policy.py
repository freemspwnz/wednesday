from domain.user import UserRole

from ...exceptions import ValidationError
from ...vo import HiddenReason, HiddenState, ImageRating, ImageState
from .decisions import Hide, NoOperation, RatingDecision, Show


class ImageRatingPolicy:
    """Catalog image rating: base 3 plus vote sum; hidden below showable rating."""

    BASE: int = 3
    SHOWABLE_RATING: int = 0
    VOTE_VALUES: frozenset[int] = frozenset({-1, 1})

    @classmethod
    def default(cls) -> ImageRating:
        return ImageRating(likes=cls.BASE, dislikes=0)

    @classmethod
    def add_vote(cls, rating: ImageRating, new: int, old: int | None) -> ImageRating:
        if new == old:
            return rating

        likes: int = rating.likes
        dislikes: int = rating.dislikes

        match new:
            case 1:
                likes += 1
            case -1:
                dislikes += 1
            case _:
                raise ValidationError("unknown vote value")

        match old:
            case 1:
                likes -= 1
            case -1:
                dislikes -= 1
            case None:
                pass
            case _:
                raise ValidationError("unknown vote value")

        return ImageRating(likes=likes, dislikes=dislikes)

    @classmethod
    def on_show(cls, actor: UserRole, current: ImageRating) -> ImageRating:
        match actor:
            case UserRole.SYSTEM:
                return current
            case UserRole.OWNER:
                return cls.default()
            case _:
                raise ValidationError("unknown actor")

    @classmethod
    def is_selectable(cls, rating: ImageRating) -> bool:
        return rating.value >= cls.SHOWABLE_RATING

    @classmethod
    def evaluate(cls, rating: ImageRating, state: ImageState) -> RatingDecision:
        if isinstance(state, HiddenState) and state.reason == HiddenReason.ADMIN:
            return NoOperation()
        elif cls.is_selectable(rating):
            return Show()
        return Hide()

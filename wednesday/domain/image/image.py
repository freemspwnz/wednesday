from dataclasses import dataclass, field
from typing import Self

from domain.kernel.vo import AwareDatetime
from domain.user import UserRole

from .events import (
    ImageEvent,
    ImageHidden,
    ImageRatingChanged,
    ImageRegistered,
    ImageShown,
)
from .exceptions import AccessDeniedError, PromptRejectedError, ValidationError
from .policies import (
    HideImage,
    ImageRatingPolicy,
    ManagementAccessPolicy,
    ManagementAction,
    ManagementAllowed,
    ManagementContext,
    ManagementDenied,
    ModerationAllowed,
    ModerationDenied,
    PromptModerationPolicy,
    ShowImage,
)
from .vo import (
    ActiveState,
    HiddenReason,
    HiddenState,
    ImageId,
    ImageMeta,
    ImagePrompts,
    ImageRating,
    ImageState,
    NormalizedPrompt,
    TelegramFileId,
)


@dataclass(slots=True, eq=False)
class Image:
    _id: ImageId
    _meta: ImageMeta
    _rating: ImageRating
    _state: ImageState
    _file_id: TelegramFileId
    _prompts: ImagePrompts
    _created_at: AwareDatetime
    _events: list[ImageEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate()

    @classmethod
    def register(
        cls,
        *,
        id: ImageId,
        meta: ImageMeta,
        file_id: TelegramFileId,
        prompts: ImagePrompts,
        created_at: AwareDatetime,
    ) -> Self:
        image = cls(
            _id=ImageId.ensure(id),
            _meta=ImageMeta.ensure(meta),
            _rating=ImageRatingPolicy.default(),
            _state=ActiveState(),
            _file_id=TelegramFileId.ensure(file_id),
            _prompts=ImagePrompts.ensure(prompts),
            _created_at=AwareDatetime.ensure(created_at),
        )
        image._record_event(
            ImageRegistered(
                image_id=image._id,
                occurred_at=created_at,
                meta=image._meta,
                prompts=image._prompts,
            ),
        )
        return image

    @classmethod
    def restore(  # noqa: PLR0913
        cls,
        *,
        id: ImageId,
        meta: ImageMeta,
        rating: ImageRating,
        state: ImageState,
        file_id: TelegramFileId,
        prompts: ImagePrompts,
        created_at: AwareDatetime,
    ) -> Self:
        return cls(
            _id=ImageId.ensure(id),
            _meta=ImageMeta.ensure(meta),
            _created_at=AwareDatetime.ensure(created_at),
            _rating=ImageRating.ensure(rating),
            _state=ImageState.ensure(state),
            _prompts=ImagePrompts.ensure(prompts),
            _file_id=TelegramFileId.ensure(file_id),
        )

    @classmethod
    def ensure(cls, image: object) -> Self:
        if not isinstance(image, cls):
            raise ValidationError(f"image must be an instance of {cls.__name__}")
        return image

    @property
    def id(self) -> ImageId:
        return self._id

    @property
    def meta(self) -> ImageMeta:
        return self._meta

    @property
    def created_at(self) -> AwareDatetime:
        return self._created_at

    @property
    def rating(self) -> ImageRating:
        return self._rating

    @property
    def state(self) -> ImageState:
        return self._state

    @property
    def prompts(self) -> ImagePrompts:
        return self._prompts

    @property
    def file_id(self) -> TelegramFileId:
        return self._file_id

    @property
    def is_hidden(self) -> bool:
        return isinstance(self._state, HiddenState)

    @property
    def is_selectable(self) -> bool:
        return ImageRatingPolicy.is_selectable(self._rating) and isinstance(self._state, ActiveState)

    def pull_events(self) -> list[ImageEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    @staticmethod
    def moderate(
        *,
        prompt: NormalizedPrompt,
        policy: PromptModerationPolicy,
    ) -> None:
        prompt = NormalizedPrompt.ensure(prompt)
        decision = policy.evaluate(str(prompt))
        match decision:
            case ModerationAllowed():
                return
            case ModerationDenied():
                raise PromptRejectedError(
                    str(decision.violation.code),
                    dict(decision.violation.meta),
                )
            case _:
                raise ValidationError("unknown moderation decision")

    def add_vote(self, *, new: int, old: int | None, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)

        new_rating = ImageRatingPolicy.add_vote(rating=self._rating, new=new, old=old)

        if new_rating != self._rating:
            old_rating = self._rating
            self._rating = new_rating
            self._record_event(
                ImageRatingChanged(
                    image_id=self._id,
                    occurred_at=at,
                    old=old_rating,
                    new=new_rating,
                ),
            )

    def hide(self, *, actor: UserRole, reason: HiddenReason, at: AwareDatetime) -> None:
        actor = UserRole.ensure(actor)
        reason = HiddenReason.ensure(reason)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor=actor, action=HideImage())

        new_state = HiddenState(reason=reason)

        if new_state == self._state:
            return

        self._state = new_state
        self._record_event(
            ImageHidden(
                image_id=self._id,
                occurred_at=at,
                actor=actor,
            ),
        )

    def show(self, *, actor: UserRole, at: AwareDatetime) -> None:
        actor = UserRole.ensure(actor)
        at = AwareDatetime.ensure(at)
        self._ensure_management_allowed(actor=actor, action=ShowImage())

        new_state = ActiveState()
        new_rating = ImageRatingPolicy.on_show(actor=actor, current=self._rating)

        if not ImageRatingPolicy.is_selectable(new_rating):
            raise ValidationError("show requires a selectable rating")

        if new_state == self._state and new_rating == self._rating:
            return

        self._rating = new_rating
        self._state = new_state
        self._record_event(
            ImageShown(
                image_id=self._id,
                occurred_at=at,
                actor=actor,
            ),
        )

    @staticmethod
    def _ensure_management_allowed(
        *,
        actor: UserRole,
        action: ManagementAction,
    ) -> None:
        context = ManagementContext(actor=actor, action=action)
        decision = ManagementAccessPolicy.evaluate(context)
        match decision:
            case ManagementAllowed():
                return
            case ManagementDenied():
                raise AccessDeniedError(str(decision.code))
            case _:
                raise ValidationError("unknown management decision")

    def _record_event(self, event: ImageEvent) -> None:
        if not isinstance(event, ImageEvent):
            raise ValidationError("event must be an ImageEvent")
        self._events.append(event)

    def _validate(self) -> None:
        ImageId.ensure(self._id)
        ImageMeta.ensure(self._meta)
        AwareDatetime.ensure(self._created_at)
        ImageState.ensure(self._state)
        ImageRating.ensure(self._rating)
        TelegramFileId.ensure(self._file_id)
        ImagePrompts.ensure(self._prompts)
        if not isinstance(self._events, list):
            raise ValidationError("events must be a list[ImageEvent]")
        for event in self._events:
            ImageEvent.ensure(event)
        self._validate_rating_state_coherence()

    def _validate_rating_state_coherence(self) -> None:
        if isinstance(self._state, ActiveState):
            if not ImageRatingPolicy.is_selectable(self._rating):
                raise ValidationError("active image must have a selectable rating")
            return

        if not isinstance(self._state, HiddenState):
            raise ValidationError("unknown image state")

        if self._state.reason == HiddenReason.ADMIN:
            return
        elif self._state.reason == HiddenReason.RATING:
            if ImageRatingPolicy.is_selectable(self._rating):
                raise ValidationError("rating-hidden image must not have a selectable rating")
        else:
            raise ValidationError("unknown hidden reason")

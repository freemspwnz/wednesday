from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Self

from domain.kernel.vo import AwareDatetime

from .events import (
    ImageAdminHidden,
    ImageAdminRestored,
    ImageEvent,
    ImageFileAttached,
    ImageRegistered,
    ImageScoreRecalculated,
)
from .exceptions import InvalidStateTransitionError, ValidationError
from .policies import ImageScorePolicy
from .vo import (
    ActiveStatus,
    HiddenReason,
    HiddenStatus,
    ImageId,
    ImageMeta,
    ImagePrompts,
    ImageStatus,
    TelegramFileId,
)


@dataclass(slots=True, eq=False)
class Image:
    _id: ImageId
    _meta: ImageMeta
    _score: int
    _status: ImageStatus
    _created_at: AwareDatetime
    _prompts: ImagePrompts | None = None
    _file_id: TelegramFileId | None = None
    _events: list[ImageEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate()

    @classmethod
    def register(
        cls,
        *,
        id: ImageId,
        meta: ImageMeta,
        created_at: AwareDatetime,
        prompts: ImagePrompts | None = None,
        file_id: TelegramFileId | None = None,
    ) -> Self:
        created_at = AwareDatetime.ensure(created_at)
        image = cls(
            _id=ImageId.ensure(id),
            _meta=ImageMeta.ensure(meta),
            _created_at=created_at,
            _score=ImageScorePolicy.BASE,
            _status=ActiveStatus(),
            _prompts=prompts,
            _file_id=file_id,
        )
        image._record_event(
            ImageRegistered(
                image_id=image._id,
                occurred_at=created_at,
                meta=image._meta,
                prompts=image._prompts,
            )
        )
        return image

    @classmethod
    def restore(  # noqa: PLR0913
        cls,
        *,
        id: ImageId,
        meta: ImageMeta,
        created_at: AwareDatetime,
        score: int,
        status: ImageStatus,
        prompts: ImagePrompts | None = None,
        file_id: TelegramFileId | None = None,
    ) -> Self:
        return cls(
            _id=id,
            _meta=meta,
            _created_at=created_at,
            _score=score,
            _status=status,
            _prompts=prompts,
            _file_id=file_id,
        )

    @classmethod
    def ensure(cls, image: Self) -> Self:
        if not isinstance(image, Image):
            raise ValidationError("image must be an Image")
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
    def score(self) -> int:
        return self._score

    @property
    def status(self) -> ImageStatus:
        return self._status

    @property
    def prompts(self) -> ImagePrompts | None:
        return self._prompts

    @property
    def file_id(self) -> TelegramFileId | None:
        return self._file_id

    @property
    def is_hidden(self) -> bool:
        return isinstance(self._status, HiddenStatus)

    @property
    def is_selectable(self) -> bool:
        return ImageScorePolicy.is_selectable(self._score) and isinstance(self._status, ActiveStatus)

    def pull_events(self) -> list[ImageEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def attach_file_id(self, file_id: TelegramFileId, *, at: AwareDatetime) -> None:
        file_id = TelegramFileId.ensure(file_id)
        at = AwareDatetime.ensure(at)
        if self._file_id is not None:
            raise InvalidStateTransitionError("file id is already attached")
        self._file_id = file_id
        self._record_event(
            ImageFileAttached(
                image_id=self._id,
                occurred_at=at,
                file_id=file_id,
            )
        )

    def recalculate_score(self, vote_values: Sequence[int], *, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)
        old_score = self._score
        old_status = self._status

        new_score = ImageScorePolicy.compute(vote_values)
        self._score = new_score
        if ImageScorePolicy.is_selectable(new_score):
            self._status = ActiveStatus()
        elif new_score <= 0 and not (
            isinstance(self._status, HiddenStatus) and self._status.reason == HiddenReason.ADMIN
        ):
            self._status = HiddenStatus(reason=HiddenReason.VOTES)

        if self._score != old_score or self._status != old_status:
            self._record_event(
                ImageScoreRecalculated(
                    image_id=self._id,
                    occurred_at=at,
                    old_score=old_score,
                    new_score=self._score,
                )
            )

    def admin_hide(self, *, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)
        if isinstance(self._status, HiddenStatus) and self._status.reason == HiddenReason.ADMIN and self._score == 0:
            return

        self._score = 0
        self._status = HiddenStatus(reason=HiddenReason.ADMIN)
        self._record_event(ImageAdminHidden(image_id=self._id, occurred_at=at))

    def admin_restore(self, *, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)
        if isinstance(self._status, ActiveStatus) and self._score == ImageScorePolicy.BASE:
            return

        self._score = ImageScorePolicy.BASE
        self._status = ActiveStatus()
        self._record_event(ImageAdminRestored(image_id=self._id, occurred_at=at))

    def _record_event(self, event: ImageEvent) -> None:
        if not isinstance(event, ImageEvent):
            raise ValidationError("event must be an ImageEvent")
        self._events.append(event)

    def _validate(self) -> None:
        ImageId.ensure(self._id)
        ImageMeta.ensure(self._meta)
        AwareDatetime.ensure(self._created_at)
        ImageStatus.ensure(self._status)
        if not isinstance(self._score, int):
            raise ValidationError("score must be an int")
        if self._prompts is not None:
            ImagePrompts.ensure(self._prompts)
        if self._file_id is not None:
            TelegramFileId.ensure(self._file_id)
        if not isinstance(self._events, list):
            raise ValidationError("events must be a list[ImageEvent]")
        for event in self._events:
            ImageEvent.ensure(event)
        self._validate_score_status_coherence()

    def _validate_score_status_coherence(self) -> None:
        if isinstance(self._status, ActiveStatus):
            if not ImageScorePolicy.is_selectable(self._score):
                raise ValidationError("active image must have a selectable score")
            return

        if not isinstance(self._status, HiddenStatus):
            raise ValidationError("unknown image status")

        if self._status.reason == HiddenReason.ADMIN:
            if self._score != 0:
                raise ValidationError("admin-hidden image must have score 0")
        elif self._status.reason == HiddenReason.VOTES:
            if ImageScorePolicy.is_selectable(self._score):
                raise ValidationError("vote-hidden image must not have a selectable score")
        else:
            raise ValidationError("unknown hidden reason")

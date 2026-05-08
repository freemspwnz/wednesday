from __future__ import annotations

from dataclasses import dataclass

from ....exceptions import ValidationError
from ....vo import ChatId, ManagementActor


@dataclass(frozen=True)
class ManagementContext:
    """Context for management access policy.

    actor: ManagementActor
    chat_id: ChatId
    """

    actor: ManagementActor
    chat_id: ChatId

    def __post_init__(self) -> None:
        ManagementActor.ensure(self.actor)
        ChatId.ensure(self.chat_id)

    @classmethod
    def ensure(cls, ctx: ManagementContext) -> ManagementContext:
        if not isinstance(ctx, cls):
            raise ValidationError("ctx must be a ManagementContext")
        return ctx

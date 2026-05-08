from dataclasses import dataclass

from ..vo import ChatProfile, ManagementActor
from .base import ChatEvent


@dataclass(frozen=True)
class ChatActivated(ChatEvent):
    actor: ManagementActor

    def __post_init__(self) -> None:
        super().__post_init__()
        ManagementActor.ensure(self.actor)


@dataclass(frozen=True)
class ChatDeactivated(ChatEvent):
    actor: ManagementActor

    def __post_init__(self) -> None:
        super().__post_init__()
        ManagementActor.ensure(self.actor)


@dataclass(frozen=True)
class ChatProfileChanged(ChatEvent):
    old_profile: ChatProfile
    new_profile: ChatProfile
    actor: ManagementActor

    def __post_init__(self) -> None:
        super().__post_init__()
        ChatProfile.ensure(self.old_profile)
        ChatProfile.ensure(self.new_profile)
        ManagementActor.ensure(self.actor)

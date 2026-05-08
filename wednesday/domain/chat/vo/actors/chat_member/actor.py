from dataclasses import dataclass

from ...chat_id import ChatId
from ..base import ManagementActor
from .member_id import ChatMemberId
from .role import ChatMemberRole


@dataclass(frozen=True)
class ChatMember(ManagementActor):
    id: ChatMemberId
    role: ChatMemberRole
    chat_id: ChatId

    def __post_init__(self) -> None:
        ChatMemberId.ensure(self.id)
        ChatMemberRole.ensure(self.role)
        ChatId.ensure(self.chat_id)

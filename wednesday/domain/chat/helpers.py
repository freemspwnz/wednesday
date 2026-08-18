from uuid import NAMESPACE_DNS, UUID, uuid5

from .vo import ChatId


def chat_id_from_tg(tg_id: int) -> ChatId:
    return ChatId(UUID(str(uuid5(NAMESPACE_DNS, f"chat:{tg_id}"))))

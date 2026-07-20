from uuid import NAMESPACE_DNS, UUID, uuid5

from ..chat import Chat
from ..exceptions import ChatNotFoundError
from ..protocols import ChatRepo
from ..vo import ChatId


async def load_or_raise(*, repo: ChatRepo, id: ChatId) -> Chat:
    chat = await repo.get_by_id(id)
    if chat is None:
        raise ChatNotFoundError(str(id))
    return chat


def chat_id_from_tg(tg_id: int) -> ChatId:
    return ChatId(UUID(str(uuid5(NAMESPACE_DNS, f"chat:{tg_id}"))))

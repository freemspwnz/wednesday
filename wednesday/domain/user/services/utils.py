from uuid import NAMESPACE_DNS, UUID, uuid5

from ..exceptions import UserNotFoundError
from ..protocols import UserRepo
from ..user import User
from ..vo import UserId


async def load_or_raise(*, repo: UserRepo, id: UserId) -> User:
    user = await repo.get_by_id(id)
    if user is None:
        raise UserNotFoundError(str(id))
    return user


def user_id_from_tg(tg_id: int) -> UserId:
    return UserId(UUID(str(uuid5(NAMESPACE_DNS, f"user:{tg_id}"))))

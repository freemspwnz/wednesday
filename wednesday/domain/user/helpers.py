from uuid import NAMESPACE_DNS, UUID, uuid5

from .vo import UserId


def user_id_from_tg(tg_id: int) -> UserId:
    return UserId(UUID(str(uuid5(NAMESPACE_DNS, f"user:{tg_id}"))))

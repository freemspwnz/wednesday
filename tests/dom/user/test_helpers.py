from domain.user.helpers import user_id_from_tg


def test_user_id_from_tg_is_deterministic() -> None:
    assert user_id_from_tg(1) == user_id_from_tg(1)

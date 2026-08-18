from domain.chat.helpers import chat_id_from_tg


def test_chat_id_from_tg_is_deterministic() -> None:
    assert chat_id_from_tg(2) == chat_id_from_tg(2)

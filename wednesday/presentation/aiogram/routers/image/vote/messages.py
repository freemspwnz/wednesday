"""User-facing texts for image catalog voting."""

VOTE_BTN_UP = "👍"

VOTE_BTN_DOWN = "👎"


def vote_btn_up(likes: int) -> str:
    return f"{VOTE_BTN_UP} {likes}"


def vote_btn_down(dislikes: int) -> str:
    return f"{VOTE_BTN_DOWN} {dislikes}"

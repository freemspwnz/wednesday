"""User-facing texts for image catalog voting."""

VOTE_BTN_UP = "👍"

VOTE_BTN_DOWN = "👎"

RANDOM_CATALOG_EMPTY = "Каталог изображений пуст для этого чата.\nСгенерируйте новое: /generate"

SCHEDULE_CATALOG_EMPTY = "Хотел отправить вам картинку, но вы уже всё посмотрели.\nЛучше сгенерируйте новую: /generate"

GENERATION_STARTED = "Генерирую изображение…"

IMAGE_UNAVAILABLE = "Изображение недоступно для отправки."


def vote_btn_up(likes: int) -> str:
    return f"{VOTE_BTN_UP} {likes}"


def vote_btn_down(dislikes: int) -> str:
    return f"{VOTE_BTN_DOWN} {dislikes}"

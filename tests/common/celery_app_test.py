"""
Отдельный Celery app для тестов.

Полностью изолирован от production кода:
- Не импортирует бот, сервисы, production задачи
- Не использует боевой config и utils.redis_client
- Конфигурируется только через тестовые переменные окружения
- Имеет тестовые очереди по умолчанию
- Регистрирует только test.ping задачу
"""

import uuid
from dataclasses import dataclass

from celery import Celery
from tenacity import retry, stop_after_attempt, wait_fixed

from tests.helpers.utils.config_test import config_test

# Получаем URL Redis для брокера и результата из тестового тестового конфига
redis_url = config_test.celery_test_redis_url

# Создаём отдельный Celery app для тестов
celery_app_test = Celery(
    "wednesday_bot_test",
    broker=redis_url,
    backend=redis_url,
)

# Минимальная конфигурация для тестов
celery_app_test.conf.task_serializer = "json"
celery_app_test.conf.accept_content = ["json"]
celery_app_test.conf.result_serializer = "json"
celery_app_test.conf.task_acks_late = True
celery_app_test.conf.task_track_started = True

# Троттлинг для долгих задач: ограничиваем время выполнения задачи
# В тестах используются быстрые задачи (test.ping), но это ограничение
# поможет предотвратить зависания при добавлении долгих задач в будущем
celery_app_test.conf.task_time_limit = 30  # Максимальное время выполнения задачи (секунды)
celery_app_test.conf.task_soft_time_limit = 25  # Мягкий лимит времени (секунды)


@dataclass(frozen=True)
class CeleryTestQueues:
    """Набор тестовых очередей, изолированных по суффиксу."""

    main: str
    images: str
    maintenance: str

    @property
    def all(self) -> tuple[str, str, str]:
        return (self.main, self.images, self.maintenance)


def generate_celery_test_queues() -> CeleryTestQueues:
    """
    Создаёт уникальные имена очередей для теста.

    Используем uuid, чтобы разные тесты не конкурировали за одну очередь.
    """
    suffix = uuid.uuid4().hex[:8]
    return CeleryTestQueues(
        main=f"test_main_{suffix}",
        images=f"test_images_{suffix}",
        maintenance=f"test_maintenance_{suffix}",
    )


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
def ensure_queues_consumed(queues: CeleryTestQueues) -> None:
    """
    Гарантирует, что worker подписан на переданные очереди.

    Используем control API, чтобы динамически добавлять потребителей без
    перезапуска worker'а.
    """
    control = celery_app_test.control
    for queue_name in queues.all:
        control.add_consumer(queue_name, reply=True)


def drop_test_consumers(queues: CeleryTestQueues) -> None:
    """Пробует снять подпись с тестовых очередей, чтобы не засорять worker."""
    control = celery_app_test.control
    for queue_name in queues.all:
        try:
            control.cancel_consumer(queue_name, reply=True)
        except Exception:
            # Не считаем ошибкой: очередь могла уже быть удалена/недоступна.
            pass


# Импортируем test.ping задачу для регистрации
from tests.common.celery_tasks_test import ping_task  # noqa: E402, F401

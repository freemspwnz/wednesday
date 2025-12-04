"""
Integration-тесты для Celery конфигурации и интеграции.
"""

from services.celery_app import celery_app


def test_celery_beat_schedule() -> None:
    """Тест конфигурации расписания Celery Beat."""
    # Проверяем, что расписание настроено
    assert hasattr(celery_app.conf, "beat_schedule")
    assert celery_app.conf.beat_schedule is not None

    # Проверяем наличие задач для среды
    # Имя задачи формируется как wednesday_frog_{time_str.replace(':', '_')}
    # По умолчанию времена: ["09:00", "12:00", "18:00"]
    assert "wednesday_frog_09_00" in celery_app.conf.beat_schedule
    assert "wednesday_frog_12_00" in celery_app.conf.beat_schedule
    assert "wednesday_frog_18_00" in celery_app.conf.beat_schedule

    # Проверяем конфигурацию задачи
    task_config = celery_app.conf.beat_schedule["wednesday_frog_09_00"]
    assert task_config["task"] == "wednesday.send_frog"
    assert task_config["args"] == ("09:00",)
    assert "options" in task_config
    assert task_config["options"]["queue"] == "wednesday"

    # Проверяем ежедневные задачи
    assert "daily_cleanup" in celery_app.conf.beat_schedule
    assert "daily_statistics" in celery_app.conf.beat_schedule

    cleanup_config = celery_app.conf.beat_schedule["daily_cleanup"]
    assert cleanup_config["task"] == "wednesday.daily_cleanup"
    assert cleanup_config["options"]["queue"] == "maintenance"

    stats_config = celery_app.conf.beat_schedule["daily_statistics"]
    assert stats_config["task"] == "wednesday.daily_statistics"
    assert stats_config["options"]["queue"] == "maintenance"


def test_celery_task_routes() -> None:
    """Тест конфигурации маршрутизации задач."""
    assert hasattr(celery_app.conf, "task_routes")
    assert celery_app.conf.task_routes is not None

    # Проверяем маршрутизацию задач по очередям
    assert "wednesday.send_frog" in celery_app.conf.task_routes
    assert celery_app.conf.task_routes["wednesday.send_frog"]["queue"] == "wednesday"

    assert "wednesday.generate_image" in celery_app.conf.task_routes
    assert celery_app.conf.task_routes["wednesday.generate_image"]["queue"] == "images"

    assert "wednesday.daily_cleanup" in celery_app.conf.task_routes
    assert celery_app.conf.task_routes["wednesday.daily_cleanup"]["queue"] == "maintenance"

    assert "wednesday.daily_statistics" in celery_app.conf.task_routes
    assert celery_app.conf.task_routes["wednesday.daily_statistics"]["queue"] == "maintenance"


def test_celery_app_configuration() -> None:
    """Тест общей конфигурации Celery приложения."""
    # Проверяем базовую конфигурацию
    assert celery_app.main == "wednesday_bot"
    assert celery_app.conf.broker_url is not None
    assert celery_app.conf.result_backend is not None

    # Проверяем настройки сериализации
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.result_serializer == "json"

    # Проверяем настройки производительности
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_max_tasks_per_child == 50
    assert celery_app.conf.task_track_started is True

    # Проверяем timezone
    assert celery_app.conf.enable_utc is False
    assert celery_app.conf.timezone is not None
    # По умолчанию должно быть Europe/Amsterdam или из конфига
    assert celery_app.conf.timezone in {"Europe/Amsterdam", "Europe/Moscow", "UTC"}


def test_celery_beat_schedule_structure() -> None:
    """Тест структуры расписания Beat."""
    for task_name, task_config in celery_app.conf.beat_schedule.items():
        # Каждая задача должна иметь обязательные поля
        assert "task" in task_config, f"Task {task_name} missing 'task' field"
        assert "schedule" in task_config, f"Task {task_name} missing 'schedule' field"
        assert "options" in task_config, f"Task {task_name} missing 'options' field"
        assert "queue" in task_config["options"], f"Task {task_name} missing queue in options"

        # Проверяем, что задача существует в celery_app
        task_name_full = task_config["task"]
        assert task_name_full in celery_app.tasks, f"Task {task_name_full} not registered"


def test_celery_task_registration() -> None:
    """Тест регистрации задач в Celery."""
    # Проверяем, что задачи зарегистрированы
    assert "wednesday.send_frog" in celery_app.tasks
    assert "wednesday.generate_image" in celery_app.tasks
    assert "wednesday.daily_cleanup" in celery_app.tasks
    assert "wednesday.daily_statistics" in celery_app.tasks

    # Проверяем, что задачи являются async задачами
    send_frog_task = celery_app.tasks["wednesday.send_frog"]
    assert hasattr(send_frog_task, "run")

    generate_image_task = celery_app.tasks["wednesday.generate_image"]
    assert hasattr(generate_image_task, "run")

    cleanup_task = celery_app.tasks["wednesday.daily_cleanup"]
    assert hasattr(cleanup_task, "run")

    stats_task = celery_app.tasks["wednesday.daily_statistics"]
    assert hasattr(stats_task, "run")

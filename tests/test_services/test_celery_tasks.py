"""
Unit-тесты для Celery задач Wednesday Frog Bot.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from services.celery_tasks import (
    CeleryServices,
    daily_cleanup_task,
    daily_statistics_task,
    generate_frog_image_task,
    is_retryable_error,
    send_wednesday_frog_task,
)

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_celery_services_lazy_init() -> None:
    """Тест lazy инициализации CeleryServices."""
    # Сбрасываем состояние перед тестом
    CeleryServices._bot = None
    CeleryServices._generator = None
    CeleryServices._initialized = False

    with (
        patch("services.celery_tasks.init_redis_pool") as mock_redis,
        patch("services.celery_tasks.init_postgres_pool") as mock_pg,
        patch("services.celery_tasks.ensure_schema") as mock_schema,
        patch("services.celery_tasks.WednesdayBot") as mock_bot_class,
    ):
        mock_bot_instance = MagicMock()
        mock_bot_instance.image_generator = MagicMock()
        mock_bot_class.return_value = mock_bot_instance

        # Первый вызов должен инициализировать
        await CeleryServices.get_bot()

        mock_redis.assert_called_once()
        mock_pg.assert_called_once()
        mock_schema.assert_called_once()
        mock_bot_class.assert_called_once()

        # Второй вызов не должен повторно инициализировать
        await CeleryServices.get_bot()
        assert mock_redis.call_count == 1
        assert mock_pg.call_count == 1
        assert mock_bot_class.call_count == 1


@pytest.mark.asyncio
async def test_is_retryable_error() -> None:
    """Тест функции определения retryable ошибок."""
    # Сетевые ошибки должны быть retryable
    assert is_retryable_error(aiohttp.ClientError()) is True
    assert is_retryable_error(aiohttp.ClientConnectorError(MagicMock(), MagicMock())) is True
    assert is_retryable_error(aiohttp.ServerTimeoutError()) is True
    assert is_retryable_error(TimeoutError()) is True
    assert is_retryable_error(ConnectionError()) is True
    assert is_retryable_error(OSError("Connection refused")) is True

    # Бизнес-логические ошибки не должны быть retryable
    assert is_retryable_error(ValueError("Invalid input")) is False
    assert is_retryable_error(KeyError("missing key")) is False
    assert is_retryable_error(TypeError("wrong type")) is False

    # Проверка строкового представления
    connection_error = Exception("Connection timeout occurred")
    assert is_retryable_error(connection_error) is True

    business_error = Exception("Invalid user ID")
    assert is_retryable_error(business_error) is False


@pytest.mark.asyncio
async def test_send_wednesday_frog_task_success() -> None:
    """Тест успешного выполнения задачи отправки."""
    # Сбрасываем состояние CeleryServices
    CeleryServices._bot = None
    CeleryServices._generator = None
    CeleryServices._initialized = False

    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    with (
        patch("services.celery_tasks.CeleryServices.get_bot") as mock_get_bot,
        patch("services.celery_tasks.log_event") as mock_log_event,
    ):
        mock_bot = AsyncMock()
        mock_bot.send_wednesday_frog = AsyncMock()
        mock_get_bot.return_value = mock_bot

        # Для задач с bind=True обходим оба декоратора и вызываем исходную функцию напрямую
        # Получаем исходную функцию через __wrapped__ дважды (Celery и log_celery_task)
        task_func = send_wednesday_frog_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__  # Обходим @celery_app.task
        if hasattr(task_func, '__func__'):
            task_func = task_func.__func__  # Получаем функцию из bound method
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__  # Обходим @log_celery_task
        # Теперь вызываем исходную функцию напрямую
        result = await task_func(mock_self, slot_time="09:00")

        assert result["status"] == "success"
        assert result["slot_time"] == "09:00"
        mock_bot.send_wednesday_frog.assert_called_once_with(slot_time="09:00")
        # Проверяем, что логирование было вызвано
        assert mock_log_event.call_count >= 2  # started и success


@pytest.mark.asyncio
async def test_send_wednesday_frog_task_retry_on_network_error() -> None:
    """Тест retry при сетевой ошибке."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"
    mock_self.retry = MagicMock(side_effect=Exception("Retry called"))

    with (
        patch("services.celery_tasks.CeleryServices.get_bot") as mock_get_bot,
        patch("services.celery_tasks.CELERY_TASK_RETRIES_TOTAL") as mock_retry_metric,
    ):
        mock_bot = AsyncMock()
        mock_bot.send_wednesday_frog = AsyncMock(side_effect=aiohttp.ClientError())
        mock_get_bot.return_value = mock_bot

        # Для тестирования retry обходим оба декоратора и вызываем исходную функцию напрямую
        # Retry логика находится в исходной функции, так что мы можем тестировать её напрямую
        task_func = send_wednesday_frog_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        if hasattr(task_func, '__func__'):
            task_func = task_func.__func__
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        with pytest.raises((Exception, aiohttp.ClientError)):
            await task_func(mock_self, slot_time="09:00")

        # Должен быть вызван retry (через self.retry в исходной функции)
        mock_self.retry.assert_called_once()
        # Проверяем, что метрика retry была обновлена
        assert mock_retry_metric.labels.called


@pytest.mark.asyncio
async def test_send_wednesday_frog_task_no_retry_on_business_error() -> None:
    """Тест отсутствия retry при бизнес-логической ошибке."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"
    mock_self.retry = MagicMock()

    with patch("services.celery_tasks.CeleryServices.get_bot") as mock_get_bot:
        mock_bot = AsyncMock()
        mock_bot.send_wednesday_frog = AsyncMock(side_effect=ValueError("Business logic error"))
        mock_get_bot.return_value = mock_bot

        # Обходим декораторы для прямого вызова исходной функции
        task_func = send_wednesday_frog_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        if hasattr(task_func, '__func__'):
            task_func = task_func.__func__
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        with pytest.raises(ValueError):
            await task_func(mock_self, slot_time="09:00")

        # Retry НЕ должен быть вызван для бизнес-логических ошибок
        mock_self.retry.assert_not_called()


@pytest.mark.asyncio
async def test_generate_frog_image_task_success() -> None:
    """Тест успешного выполнения задачи генерации."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    with patch("services.celery_tasks.CeleryServices.get_generator") as mock_get_gen:
        mock_gen = AsyncMock()
        mock_gen.generate_frog_image = AsyncMock(return_value=(b"image_data", "caption"))
        mock_get_gen.return_value = mock_gen

        task_func = generate_frog_image_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        if hasattr(task_func, '__func__'):
            task_func = task_func.__func__
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        result = await task_func(mock_self, user_id=123)

        assert result["status"] == "success"
        assert "image_size" in result
        assert result["image_size"] == len(b"image_data")
        mock_gen.generate_frog_image.assert_called_once_with(user_id=123)


@pytest.mark.asyncio
async def test_generate_frog_image_task_failed() -> None:
    """Тест задачи генерации при неудаче."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    with patch("services.celery_tasks.CeleryServices.get_generator") as mock_get_gen:
        mock_gen = AsyncMock()
        mock_gen.generate_frog_image = AsyncMock(return_value=None)
        mock_get_gen.return_value = mock_gen

        task_func = generate_frog_image_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        if hasattr(task_func, '__func__'):
            task_func = task_func.__func__
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        result = await task_func(mock_self, user_id=123)

        assert result["status"] == "failed"
        assert "error" in result
        assert result["error"] == "Генерация вернула None"


@pytest.mark.asyncio
async def test_generate_frog_image_task_retry_on_network_error() -> None:
    """Тест retry при сетевой ошибке в задаче генерации."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"
    mock_self.retry = MagicMock(side_effect=Exception("Retry called"))

    with (
        patch("services.celery_tasks.CeleryServices.get_generator") as mock_get_gen,
        patch("services.celery_tasks.CELERY_TASK_RETRIES_TOTAL") as mock_retry_metric,
    ):
        mock_gen = AsyncMock()
        mock_gen.generate_frog_image = AsyncMock(side_effect=aiohttp.ClientError())
        mock_get_gen.return_value = mock_gen

        # Для тестирования retry обходим оба декоратора и вызываем исходную функцию напрямую
        task_func = generate_frog_image_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        if hasattr(task_func, '__func__'):
            task_func = task_func.__func__
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        with pytest.raises((Exception, aiohttp.ClientError)):
            await task_func(mock_self, user_id=123)

        mock_self.retry.assert_called_once()
        assert mock_retry_metric.labels.called
        mock_retry_metric.labels.assert_called_once_with(task_name="generate_frog_image")


@pytest.mark.asyncio
async def test_daily_cleanup_task_success() -> None:
    """Тест успешного выполнения задачи очистки."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    # Сбрасываем состояние CeleryServices
    CeleryServices._bot = None
    CeleryServices._generator = None
    CeleryServices._initialized = False

    with (
        patch("services.celery_tasks.CeleryServices.get_bot") as mock_get_bot,
        patch("utils.dispatch_registry.DispatchRegistry") as mock_registry_class,
    ):
        mock_bot = AsyncMock()
        mock_get_bot.return_value = mock_bot

        mock_registry = AsyncMock()
        mock_registry.cleanup_old = AsyncMock()
        mock_registry_class.return_value = mock_registry

        task_func = daily_cleanup_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        if hasattr(task_func, '__func__'):
            task_func = task_func.__func__
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        result = await task_func(mock_self)

        assert result["status"] == "success"
        mock_registry.cleanup_old.assert_called_once()


@pytest.mark.asyncio
async def test_daily_statistics_task_success() -> None:
    """Тест успешного выполнения задачи статистики."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    # Сбрасываем состояние CeleryServices
    CeleryServices._bot = None
    CeleryServices._generator = None
    CeleryServices._initialized = False

    with patch("services.celery_tasks.CeleryServices.get_bot") as mock_get_bot:
        mock_bot = AsyncMock()
        mock_get_bot.return_value = mock_bot

        task_func = daily_statistics_task
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        if hasattr(task_func, '__func__'):
            task_func = task_func.__func__
        if hasattr(task_func, '__wrapped__'):
            task_func = task_func.__wrapped__
        result = await task_func(mock_self)

        assert result["status"] == "success"


@pytest.mark.asyncio
async def test_celery_services_shutdown() -> None:
    """Тест graceful shutdown CeleryServices."""
    # Инициализируем сервисы
    CeleryServices._bot = MagicMock()
    CeleryServices._generator = MagicMock()
    CeleryServices._initialized = True

    # Мокаем aclose методы для bot и generator
    mock_bot_aclose = AsyncMock()
    mock_generator_aclose = AsyncMock()
    CeleryServices._bot.aclose = mock_bot_aclose
    CeleryServices._generator.aclose = mock_generator_aclose

    with (
        patch("services.celery_tasks.close_postgres_pool", new_callable=AsyncMock) as mock_close_pg,
        patch("services.celery_tasks.close_redis", new_callable=AsyncMock) as mock_close_redis,
    ):
        await CeleryServices.shutdown()

        # Проверяем, что ресурсы были закрыты
        mock_close_pg.assert_awaited_once()
        mock_close_redis.assert_awaited_once()

        # Проверяем, что состояние сброшено
        assert CeleryServices._bot is None
        assert CeleryServices._generator is None
        assert CeleryServices._initialized is False

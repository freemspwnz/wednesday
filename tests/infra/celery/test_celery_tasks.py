"""
Unit-тесты для Celery задач Wednesday Frog Bot.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from infra.celery.context import create_factories, get_services_context
from infra.celery.tasks import (
    daily_cleanup_task,
    daily_statistics_task,
    generate_frog_image_task,
    is_retryable_error,
    send_wednesday_frog_task,
)
from shared.config import Config

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_services_context_lazy_init(reset_singletons: Any) -> None:
    """Тест lazy инициализации services context."""

    with (
        patch("infra.celery.context.PostgresPoolFactory") as mock_pool_factory_class,
        patch("infra.celery.context.RedisClientFactory") as mock_redis_factory_class,
        patch("infra.celery.context.ensure_schema") as mock_schema,
        patch("infra.celery.context.build_bot") as mock_build_bot,
    ):
        # Создаём моки фабрик
        mock_pool_factory = MagicMock()
        mock_redis_factory = MagicMock()
        mock_pool_factory_class.return_value = mock_pool_factory
        mock_redis_factory_class.return_value = mock_redis_factory

        # Моки для пулов
        mock_postgres_pool = AsyncMock()
        mock_redis_client = AsyncMock()
        mock_pool_factory.get_pool = AsyncMock(return_value=mock_postgres_pool)
        mock_redis_factory.get_client = AsyncMock(return_value=mock_redis_client)

        mock_bot_instance = MagicMock()
        mock_build_bot.return_value = mock_bot_instance

        config_obj = Config()
        pool_factory, redis_factory = create_factories(config_obj)

        # Первый вызов должен инициализировать
        context = await get_services_context(
            pool_factory=pool_factory,
            redis_factory=redis_factory,
            config_obj=config_obj,
        )
        assert "bot" in context

        mock_schema.assert_called_once()
        mock_build_bot.assert_called_once()

        # Второй вызов не должен повторно инициализировать
        context2 = await get_services_context(
            pool_factory=pool_factory,
            redis_factory=redis_factory,
            config_obj=config_obj,
        )
        assert context is context2  # Должен вернуть тот же контекст
        assert mock_schema.call_count == 1
        assert mock_build_bot.call_count == 1


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
async def test_send_wednesday_frog_task_success(reset_singletons: Any) -> None:
    """Тест успешного выполнения задачи отправки."""

    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    with (
        patch("infra.celery.context.get_services_context") as mock_get_context,
        patch("infra.celery.context.log_event") as mock_log_event,
    ):
        mock_bot = AsyncMock()
        mock_bot.send_wednesday_frog = AsyncMock()
        mock_get_context.return_value = {"bot": mock_bot}

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
        patch("infra.celery.context.get_services_context") as mock_get_context,
        patch("infra.celery.context.CELERY_TASK_RETRIES_TOTAL") as mock_retry_metric,
    ):
        mock_bot = AsyncMock()
        mock_bot.send_wednesday_frog = AsyncMock(side_effect=aiohttp.ClientError())
        mock_get_context.return_value = {"bot": mock_bot}

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

    with patch("infra.celery.context.get_services_context") as mock_get_context:
        mock_bot = AsyncMock()
        mock_bot.send_wednesday_frog = AsyncMock(side_effect=ValueError("Business logic error"))
        mock_get_context.return_value = {"bot": mock_bot}

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

    with patch("infra.celery.context.get_services_context") as mock_get_context:
        mock_image_service = AsyncMock()
        mock_image_service.generate_frog_image = AsyncMock(return_value=(b"image_data", "caption"))
        mock_get_context.return_value = {"image_service": mock_image_service}

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
        mock_image_service.generate_frog_image.assert_called_once_with(user_id=123)


@pytest.mark.asyncio
async def test_generate_frog_image_task_failed() -> None:
    """Тест задачи генерации при неудаче."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    with patch("infra.celery.context.get_services_context") as mock_get_context:
        mock_image_service = AsyncMock()
        mock_image_service.generate_frog_image = AsyncMock(return_value=None)
        mock_get_context.return_value = {"image_service": mock_image_service}

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
        patch("infra.celery.context.get_services_context") as mock_get_context,
        patch("infra.celery.context.CELERY_TASK_RETRIES_TOTAL") as mock_retry_metric,
    ):
        mock_image_service = AsyncMock()
        mock_image_service.generate_frog_image = AsyncMock(side_effect=aiohttp.ClientError())
        mock_get_context.return_value = {"image_service": mock_image_service}

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
async def test_daily_cleanup_task_success(reset_singletons: Any) -> None:
    """Тест успешного выполнения задачи очистки."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    with (
        patch("infra.celery.context.get_services_context") as mock_get_context,
        patch("infra.repos.dispatch_registry.DispatchRegistry") as mock_registry_class,
    ):
        mock_pool = MagicMock()
        mock_get_context.return_value = {"postgres_pool": mock_pool}

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
async def test_daily_statistics_task_success(reset_singletons: Any) -> None:
    """Тест успешного выполнения задачи статистики."""
    mock_self = MagicMock()
    mock_self.request = MagicMock()
    mock_self.request.id = "test-task-id"

    with patch("infra.celery.context.get_services_context") as mock_get_context:
        mock_get_context.return_value = {}

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
async def test_services_context_shutdown() -> None:
    """Тест graceful shutdown services context."""
    # Инициализируем контекст сервисов
    import infra.celery.context as celery_context_module
    from infra.celery.context import shutdown_services

    mock_bot = MagicMock()
    mock_bot.services = MagicMock()
    mock_bot.services.cleanup = AsyncMock()

    celery_context_module._services_context = {
        "bot": mock_bot,
        "postgres_pool": MagicMock(),
        "redis_client": MagicMock(),
    }

    with (
        patch("infra.celery.context.close_postgres_pool", new_callable=AsyncMock) as mock_close_pg,
        patch("infra.celery.context.close_redis", new_callable=AsyncMock) as mock_close_redis,
    ):
        await shutdown_services()

        # Проверяем, что ресурсы были закрыты
        mock_close_pg.assert_awaited_once()
        mock_close_redis.assert_awaited_once()
        mock_bot.services.cleanup.assert_awaited_once()

        # Проверяем, что состояние сброшено
        assert celery_context_module._services_context is None

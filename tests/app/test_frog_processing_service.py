"""Unit-тесты для FrogProcessingService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.frog_processing_service import FrogProcessingService
from shared.base.exceptions import UnexpectedImageError
from shared.protocols import ILogger, IUsageTracker

pytestmark = [pytest.mark.unit]


@pytest.fixture
def mock_image_service() -> MagicMock:
    """Создаёт мок ImageService."""
    service = MagicMock()
    service.generate_frog_image = AsyncMock(return_value=(b"image_data", "caption"))
    service.get_random_saved_image = AsyncMock(return_value=(b"fallback_image", "fallback_caption"))
    return service


@pytest.fixture
def mock_delivery_service() -> MagicMock:
    """Создаёт мок FrogDeliveryService."""
    service = MagicMock()
    service.send_image_to_user = AsyncMock(return_value=True)
    service.send_fallback_to_user = AsyncMock()
    return service


@pytest.fixture
def mock_usage_tracker() -> MagicMock:
    """Создаёт мок IUsageTracker."""
    tracker = MagicMock(spec=IUsageTracker)
    tracker.increment = AsyncMock()
    return tracker


@pytest.fixture
def mock_admin_notifier() -> MagicMock:
    """Создаёт мок AdminNotificationService."""
    notifier = MagicMock()
    notifier.notify_generation_failure = AsyncMock()
    return notifier


@pytest.fixture
def mock_logger() -> MagicMock:
    """Создаёт мок ILogger."""
    logger = MagicMock(spec=ILogger)
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    return logger


@pytest.fixture
def frog_processing_service(
    mock_image_service: MagicMock,
    mock_delivery_service: MagicMock,
    mock_usage_tracker: MagicMock,
    mock_admin_notifier: MagicMock,
    mock_logger: MagicMock,
) -> FrogProcessingService:
    """Создаёт экземпляр FrogProcessingService с моками."""
    return FrogProcessingService(
        image_service=mock_image_service,
        delivery_service=mock_delivery_service,
        usage_tracker=mock_usage_tracker,
        admin_notifier=mock_admin_notifier,
        logger=mock_logger,
    )


@pytest.mark.asyncio
async def test_process_frog_request_success(
    frog_processing_service: FrogProcessingService,
    mock_image_service: MagicMock,
    mock_delivery_service: MagicMock,
    mock_usage_tracker: MagicMock,
) -> None:
    """Тест успешной обработки запроса."""
    result = await frog_processing_service.process_frog_request(
        chat_id=123,
        user_id=456,
        status_message_id=789,
    )

    assert result["status"] == "success"
    mock_image_service.generate_frog_image.assert_called_once_with(user_id=456)
    mock_delivery_service.send_image_to_user.assert_called_once_with(
        chat_id=123,
        user_id=456,
        image_data=b"image_data",
        caption="caption",
        status_message_id=789,
    )
    mock_usage_tracker.increment.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_process_frog_request_generation_failure(
    frog_processing_service: FrogProcessingService,
    mock_image_service: MagicMock,
    mock_delivery_service: MagicMock,
    mock_admin_notifier: MagicMock,
) -> None:
    """Тест обработки ошибки генерации."""
    from shared.base.exceptions import ImageGenerationError

    mock_image_service.generate_frog_image.side_effect = ImageGenerationError("Generation failed")

    result = await frog_processing_service.process_frog_request(
        chat_id=123,
        user_id=456,
        status_message_id=789,
    )

    assert result["status"] == "failed"
    assert "error" in result
    mock_delivery_service.send_fallback_to_user.assert_called_once()
    mock_admin_notifier.notify_generation_failure.assert_called_once()


@pytest.mark.asyncio
async def test_process_frog_request_unexpected_error(
    frog_processing_service: FrogProcessingService,
    mock_image_service: MagicMock,
    mock_delivery_service: MagicMock,
    mock_admin_notifier: MagicMock,
) -> None:
    """Тест обработки неожиданной ошибки."""
    mock_image_service.generate_frog_image.side_effect = UnexpectedImageError("Unexpected error")

    result = await frog_processing_service.process_frog_request(
        chat_id=123,
        user_id=456,
        status_message_id=789,
    )

    assert result["status"] == "failed"
    assert "error" in result
    mock_delivery_service.send_fallback_to_user.assert_called_once()
    mock_admin_notifier.notify_generation_failure.assert_called_once()


@pytest.mark.asyncio
async def test_process_frog_request_messaging_error(
    frog_processing_service: FrogProcessingService,
    mock_image_service: MagicMock,
    mock_delivery_service: MagicMock,
) -> None:
    """Тест обработки ошибки отправки сообщения."""
    mock_delivery_service.send_image_to_user.return_value = False

    result = await frog_processing_service.process_frog_request(
        chat_id=123,
        user_id=456,
        status_message_id=789,
    )

    assert result["status"] == "failed"
    assert "error" in result


@pytest.mark.asyncio
async def test_process_frog_request_no_status_message(
    frog_processing_service: FrogProcessingService,
    mock_delivery_service: MagicMock,
) -> None:
    """Тест обработки запроса без статусного сообщения."""
    result = await frog_processing_service.process_frog_request(
        chat_id=123,
        user_id=456,
        status_message_id=None,
    )

    assert result["status"] == "success"
    mock_delivery_service.send_image_to_user.assert_called_once_with(
        chat_id=123,
        user_id=456,
        image_data=b"image_data",
        caption="caption",
        status_message_id=None,
    )


@pytest.mark.asyncio
async def test_process_frog_request_no_usage_tracker(
    mock_image_service: MagicMock,
    mock_delivery_service: MagicMock,
    mock_admin_notifier: MagicMock,
    mock_logger: MagicMock,
) -> None:
    """Тест обработки запроса без usage_tracker."""
    service = FrogProcessingService(
        image_service=mock_image_service,
        delivery_service=mock_delivery_service,
        usage_tracker=None,
        admin_notifier=mock_admin_notifier,
        logger=mock_logger,
    )

    result = await service.process_frog_request(
        chat_id=123,
        user_id=456,
    )

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_process_frog_request_no_admin_notifier(
    mock_image_service: MagicMock,
    mock_delivery_service: MagicMock,
    mock_usage_tracker: MagicMock,
    mock_logger: MagicMock,
) -> None:
    """Тест обработки запроса без admin_notifier."""
    from shared.base.exceptions import ImageGenerationError

    service = FrogProcessingService(
        image_service=mock_image_service,
        delivery_service=mock_delivery_service,
        usage_tracker=mock_usage_tracker,
        admin_notifier=None,
        logger=mock_logger,
    )

    mock_image_service.generate_frog_image.side_effect = ImageGenerationError("Generation failed")

    result = await service.process_frog_request(
        chat_id=123,
        user_id=456,
    )

    assert result["status"] == "failed"
    # Уведомление админов не должно быть вызвано
    assert not hasattr(service, "_admin_notifier") or service._admin_notifier is None

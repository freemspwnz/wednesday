"""Tests for SberClient adapter."""

from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest

from app.exceptions import HttpTransportError
from domain.image import ImageGenError, TextGenError
from infra.network.httpx.providers.sber.adapter import SberClient


def _timeouts() -> dict[str, httpx2.Timeout]:
    t = httpx2.Timeout(5.0)
    return {"base": t, "image": t, "prompt": t, "models": t}


@pytest.mark.unit
class TestSberClient:
    @pytest.mark.asyncio
    async def test_generate_text_success(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "hello frog"}}]}
        client.post = AsyncMock(return_value=response)

        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        text = await sber.generate_text("gigachat-2-lite", "sys", "user")
        assert text == "hello frog"
        client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_text_maps_app_error(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.post = AsyncMock(side_effect=HttpTransportError("down", method="POST", url="https://x"))
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        with pytest.raises(TextGenError):
            await sber.generate_text("m", "s", "u")

    @pytest.mark.asyncio
    async def test_generate_image_success(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        chat_response = MagicMock()
        chat_response.json.return_value = {
            "choices": [{"message": {"content": '<img src="file-123"/>'}}],
        }
        file_response = MagicMock()
        file_response.content = b"PNGDATA"
        client.post = AsyncMock(return_value=chat_response)
        client.get = AsyncMock(return_value=file_response)

        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        content = await sber.generate_image("gigachat-2-pro", "sys", "draw frog")
        assert content == b"PNGDATA"
        client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_image_missing_src_raises(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "no image here"}}]}
        client.post = AsyncMock(return_value=response)
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        with pytest.raises(ImageGenError, match="Image id not found"):
            await sber.generate_image("m", "s", "u")

    @pytest.mark.asyncio
    async def test_check_health(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value=MagicMock())
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        assert await sber.check_health() is True

        client.get = AsyncMock(side_effect=HttpTransportError("down", method="GET", url="https://x"))
        assert await sber.check_health() is False

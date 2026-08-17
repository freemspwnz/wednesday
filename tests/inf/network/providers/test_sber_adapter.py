"""Tests for SberClient adapter."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest

from app.exceptions import HttpTransportError
from domain.image import GenerationError
from infra.network.httpx.providers.sber.adapter import SberClient


def _timeouts(*, read: float = 5.0) -> dict[str, httpx2.Timeout]:
    t = httpx2.Timeout(read)
    return {"base": t, "image": t, "prompt": t, "models": t}


def _chat_response(*, src: str = "file-123") -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"message": {"content": f'<img src="{src}"/>'}}],
    }
    return response


def _file_response(*, content: bytes = b"PNGDATA") -> MagicMock:
    response = MagicMock()
    response.content = content
    return response


def _text_response(*, content: str = "hello frog") -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


@pytest.mark.unit
class TestSberClient:
    @pytest.mark.asyncio
    async def test_generate_text_success(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.post = AsyncMock(return_value=_text_response())

        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        text = await sber.generate_text("gigachat-2-lite", "sys", "user")
        assert text == "hello frog"
        client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_text_maps_app_error(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.post = AsyncMock(side_effect=HttpTransportError("down", method="POST", url="https://x"))
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        with pytest.raises(GenerationError):
            await sber.generate_text("m", "s", "u")

    @pytest.mark.asyncio
    async def test_generate_image_success(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.post = AsyncMock(return_value=_chat_response())
        client.get = AsyncMock(return_value=_file_response())

        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        content = await sber.generate_image("gigachat-2-pro", "sys", "draw frog")
        assert content == b"PNGDATA"
        client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_image_missing_src_raises(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.post = AsyncMock(return_value=_text_response(content="no image here"))
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        with pytest.raises(GenerationError, match="Image id not found"):
            await sber.generate_image("m", "s", "u")

    @pytest.mark.asyncio
    async def test_generate_image_releases_slot_after_error(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.post = AsyncMock(
            side_effect=[
                HttpTransportError("down", method="POST", url="https://x"),
                _chat_response(),
            ],
        )
        client.get = AsyncMock(return_value=_file_response())
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)

        with pytest.raises(GenerationError):
            await sber.generate_image("m", "s", "u")

        content = await sber.generate_image("m", "s", "u")
        assert content == b"PNGDATA"

    @pytest.mark.asyncio
    async def test_check_health(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value=MagicMock())
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)
        assert await sber.check_health() is True

        client.get = AsyncMock(side_effect=HttpTransportError("down", method="GET", url="https://x"))
        assert await sber.check_health() is False

    @pytest.mark.asyncio
    async def test_concurrent_generate_image_does_not_overlap(self, mock_logger: MagicMock) -> None:
        log: list[str] = []
        in_flight = 0
        max_in_flight = 0
        hold = asyncio.Event()
        entered = asyncio.Event()

        async def post(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            log.append("post")
            entered.set()
            await hold.wait()
            in_flight -= 1
            return _chat_response()

        async def get(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            log.append("get")
            in_flight -= 1
            return _file_response()

        client = MagicMock()
        client.post = post
        client.get = get
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)

        first = asyncio.create_task(sber.generate_image("m", "s", "u1"))
        await entered.wait()
        second = asyncio.create_task(sber.generate_image("m", "s", "u2"))
        await asyncio.sleep(0.05)

        assert log == ["post"]
        assert max_in_flight == 1

        hold.set()
        first_content, second_content = await asyncio.gather(first, second)
        assert first_content == b"PNGDATA"
        assert second_content == b"PNGDATA"
        assert log == ["post", "get", "post", "get"]
        assert max_in_flight == 1

    @pytest.mark.asyncio
    async def test_generate_text_does_not_overlap_generate_image(
        self,
        mock_logger: MagicMock,
    ) -> None:
        log: list[str] = []
        in_flight = 0
        max_in_flight = 0
        hold = asyncio.Event()
        entered = asyncio.Event()

        posts = 0

        async def post(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal in_flight, max_in_flight, posts
            posts += 1
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            log.append("post")
            entered.set()
            await hold.wait()
            in_flight -= 1
            return _chat_response() if posts == 1 else _text_response()

        async def get(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            log.append("get")
            in_flight -= 1
            return _file_response()

        client = MagicMock()
        client.post = post
        client.get = get
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)

        image_task = asyncio.create_task(sber.generate_image("m", "s", "draw"))
        await entered.wait()
        text_task = asyncio.create_task(sber.generate_text("m", "s", "enrich"))
        await asyncio.sleep(0.05)

        assert log == ["post"]
        assert max_in_flight == 1

        hold.set()
        image, text = await asyncio.gather(image_task, text_task)
        assert image == b"PNGDATA"
        assert text == "hello frog"
        assert log == ["post", "get", "post"]
        assert max_in_flight == 1

    @pytest.mark.asyncio
    async def test_slot_busy_raises_generation_error(self, mock_logger: MagicMock) -> None:
        hold = asyncio.Event()
        entered = asyncio.Event()

        async def post(*_args: object, **_kwargs: object) -> MagicMock:
            entered.set()
            await hold.wait()
            return _chat_response()

        client = MagicMock()
        client.post = post
        client.get = AsyncMock(return_value=_file_response())
        sber = SberClient(
            client=client,
            auth=MagicMock(),
            timeouts=_timeouts(read=0.05),
            logger=mock_logger,
        )

        first = asyncio.create_task(sber.generate_image("m", "s", "u1"))
        await entered.wait()
        with pytest.raises(GenerationError, match="GigaChat slot busy"):
            await sber.generate_image("m", "s", "u2")
        hold.set()
        assert await first == b"PNGDATA"

    @pytest.mark.asyncio
    async def test_check_health_does_not_wait_for_slot(self, mock_logger: MagicMock) -> None:
        hold = asyncio.Event()
        entered = asyncio.Event()

        async def post(*_args: object, **_kwargs: object) -> MagicMock:
            entered.set()
            await hold.wait()
            return _chat_response()

        client = MagicMock()
        client.post = post
        client.get = AsyncMock(return_value=_file_response())
        sber = SberClient(client=client, auth=MagicMock(), timeouts=_timeouts(), logger=mock_logger)

        image_task = asyncio.create_task(sber.generate_image("m", "s", "u"))
        await entered.wait()
        assert await sber.check_health() is True
        hold.set()
        assert await image_task == b"PNGDATA"

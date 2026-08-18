import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import ClassVar, Final

from httpx2 import Auth, Timeout

from app.exceptions import AppError
from app.protocols import Logger
from domain.image import GenerationError, Generator

from ...client import HttpClient


class SberClient(Generator):
    """GigaChat adapter implementing domain generator protocol.

    ``generate_text`` and ``generate_image`` share a process-local
    ``asyncio.Semaphore(1)``. A second call waits for the in-flight slot
    (bounded by that operation's read timeout) instead of overlapping HTTP.
    ``generate_image`` holds the slot for both ``POST /chat/completions`` and
    ``GET /files/.../content``. ``check_health`` is not serialized. The slot
    is not shared across processes.
    """

    _TEXT_TEMPERATURE: ClassVar[float] = 0.9
    _TEXT_TOP_P: ClassVar[float] = 0.95
    _IMG_SRC_REGEX: Final[re.Pattern[str]] = re.compile(r'src="([^"]+)"')

    def __init__(
        self,
        *,
        client: HttpClient,
        auth: Auth,
        timeouts: dict[str, Timeout],
        logger: Logger,
    ) -> None:
        self._client = client
        self._auth = auth
        self._timeouts = timeouts
        self._slot = asyncio.Semaphore(1)
        self._logger = logger.bind(module=self.__class__.__name__)

    @property
    def client(self) -> HttpClient:
        return self._client

    async def generate_image(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> bytes:
        self._logger.info("GigaChat generation started", operation="image", model=model)
        async with self._with_slot(self._timeouts["image"].read):
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "function_call": "auto",
            }

            try:
                response = await self._client.post(
                    "/chat/completions",
                    json=payload,
                    timeout=self._timeouts["image"],
                    auth=self._auth,
                )
                data = response.json()
                content: str = data["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("message content must be str")
                match = self._IMG_SRC_REGEX.search(content)
                if not match:
                    self._logger.error(
                        "Image id not found in GigaChat response",
                        content_preview=content[:200],
                        content_len=len(content),
                    )
                    raise GenerationError("Image id not found in GigaChat response")

                file_id = match.group(1)
                image_response = await self._client.get(
                    f"/files/{file_id}/content",
                    timeout=self._timeouts["image"],
                    auth=self._auth,
                )
                image_bytes = image_response.content
                self._logger.info(
                    "GigaChat generation finished",
                    operation="image",
                    model=model,
                    bytes=len(image_bytes),
                )
                return image_bytes
            except GenerationError:
                raise
            except AppError as exc:
                # HttpClient / SberAuth already logged unexpected transport failures.
                raise GenerationError(str(exc)) from exc
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                self._logger.error(
                    "Unexpected GigaChat response format for image generation",
                    exc_info=True,
                )
                raise GenerationError("Unexpected GigaChat image response format") from exc
            except Exception as exc:
                self._logger.error(
                    "Unexpected error during image generation",
                    exc_info=True,
                )
                raise GenerationError("Unexpected error during image generation") from exc

    async def generate_text(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self._logger.info("GigaChat generation started", operation="text", model=model)
        async with self._with_slot(self._timeouts["prompt"].read):
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self._TEXT_TEMPERATURE,
                "top_p": self._TEXT_TOP_P,
            }

            try:
                response = await self._client.post(
                    "/chat/completions",
                    json=payload,
                    timeout=self._timeouts["prompt"],
                    auth=self._auth,
                )
                data = response.json()
                content: str = data["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("message content must be str")
                self._logger.info(
                    "GigaChat generation finished",
                    operation="text",
                    model=model,
                    chars=len(content),
                )
                return content
            except AppError as exc:
                raise GenerationError(str(exc)) from exc
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                self._logger.error(
                    "Unexpected GigaChat response format for text generation",
                    exc_info=True,
                )
                raise GenerationError("Unexpected GigaChat text response format") from exc
            except Exception as exc:
                self._logger.error(
                    "Unexpected error during text generation",
                    exc_info=True,
                )
                raise GenerationError("Unexpected error during text generation") from exc

    async def check_health(self) -> bool:
        """Check health of the Sber API."""
        try:
            await self._client.get("/models", timeout=self._timeouts["models"], auth=self._auth)
            return True
        except AppError:
            return False
        except Exception:
            self._logger.error("Failed to check health", exc_info=True)
            return False

    @asynccontextmanager
    async def _with_slot(self, timeout: float | None) -> AsyncIterator[None]:
        """Wait up to ``timeout`` seconds for the GigaChat in-flight slot.

        ``None`` waits indefinitely. Raises ``GenerationError`` if the slot
        does not become free in time. The slot is always released, including
        when the caller fails.
        """
        try:
            await asyncio.wait_for(self._slot.acquire(), timeout=timeout)
        except TimeoutError:
            self._logger.warning("GigaChat slot busy", timeout=timeout)
            raise GenerationError("GigaChat slot busy") from None
        try:
            yield
        finally:
            self._slot.release()

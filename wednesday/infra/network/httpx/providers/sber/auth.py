import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from http import HTTPStatus

from httpx2 import AsyncClient, Auth, Request, Response

from app.exceptions import HttpAuthError, UnexpectedHttpError
from app.protocols import Logger

from ...errors import map_httpx_error


class SberAuth(Auth):
    """OAuth2 client-credentials flow for GigaChat (Sber) APIs."""

    _TOKEN_SKEW = 10

    def __init__(
        self,
        *,
        client: AsyncClient,
        url: str,
        key: str,
        scope: str,
        logger: Logger,
    ) -> None:
        self._client = client
        self._url = url
        self._key = key
        self._scope = scope
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()
        self._logger = logger.bind(module=self.__class__.__name__)

    def _needs_refresh(self) -> bool:
        return not self._access_token or time.time() >= self._expires_at - self._TOKEN_SKEW

    async def _ensure_token(self) -> None:
        if not self._needs_refresh():
            return
        async with self._lock:
            if not self._needs_refresh():
                return
            await self._fetch_token()

    async def _fetch_token(self) -> None:
        """Request new token from Sber OAuth."""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self._key}",
        }
        payload = {"scope": self._scope}

        self._logger.info("Fetching auth token", auth_url=self._url)
        try:
            response = await self._client.request(
                "POST",
                self._url,
                headers=headers,
                data=payload,
                auth=None,
            )
            response.raise_for_status()
            data = response.json()
            access_token = data["access_token"]
            expires_at = data["expires_at"] / 1000
        except (KeyError, TypeError, ValueError) as exc:
            self._logger.error(
                "Invalid OAuth token response",
                auth_url=self._url,
                exc_info=True,
            )
            raise HttpAuthError(
                f"Invalid OAuth token response: POST {self._url}",
                method="POST",
                url=self._url,
            ) from exc
        except Exception as exc:
            mapped = map_httpx_error(exc, method="POST", url=self._url)
            if isinstance(mapped, UnexpectedHttpError):
                self._logger.error(
                    "Failed to fetch auth token",
                    auth_url=self._url,
                    exc_info=True,
                )
            raise HttpAuthError(
                f"OAuth token request failed: POST {self._url}",
                method="POST",
                url=self._url,
            ) from mapped

        self._access_token = access_token
        self._expires_at = expires_at
        self._logger.info("Auth token fetched", auth_url=self._url)

    async def async_auth_flow(self, request: Request) -> AsyncGenerator[Request, Response]:
        await self._ensure_token()
        token = self._access_token
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            self._logger.warning("Received 401, refreshing token", status_code=response.status_code)
            async with self._lock:
                if self._access_token == token:
                    await self._fetch_token()
            request.headers["Authorization"] = f"Bearer {self._access_token}"
            yield request

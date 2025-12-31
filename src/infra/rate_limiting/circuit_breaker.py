"""Сервис circuit breaker для защиты от перегрузки внешних API."""

from __future__ import annotations

import time

import redis.asyncio as redis

from shared.base.exceptions import CircuitBreakerOpen
from shared.base.redis_backend_service import RedisBackendService


class CircuitBreakerService(RedisBackendService):
    """Сервис circuit breaker для защиты от перегрузки внешних API.

    Использует Redis для хранения состояния.
    Circuit breaker открывается при превышении порога ошибок и блокирует
    запросы на время cooldown.
    """

    def __init__(  # noqa: PLR0913
        self,
        redis_client: redis.Redis,
        *,
        key: str = "cb:default",
        threshold: int = 5,
        window: int = 300,
        cooldown: int | None = None,
        prefix: str = "",
    ) -> None:
        """Инициализирует circuit breaker.

        Args:
            redis_client: Экземпляр Redis клиента.
            key: Логический ключ ресурса (например, 'kandinsky_api').
            threshold: Количество ошибок до открытия circuit-breaker (по умолчанию 5).
            window: Окно жизни счётчика ошибок в секундах через EXPIRE (по умолчанию 300).
            cooldown: Минимальный интервал после последней ошибки в секундах, в течение
                которого circuit считается открытым. По умолчанию равен window.
            prefix: Префикс для всех ключей (по умолчанию "").
        """
        super().__init__(redis_client=redis_client, prefix=prefix)
        self.key = self._key(key)
        self.threshold = threshold
        self.window = window
        self.cooldown = cooldown if cooldown is not None else window

    @staticmethod
    def _now() -> float:
        """Возвращает текущее время в секундах."""
        return time.time()

    async def is_open(self) -> bool:
        """Проверяет, открыт ли circuit breaker.

        Circuit считается открытым, если количество ошибок превышает threshold
        и с момента последней ошибки прошло меньше cooldown секунд.

        Returns:
            True если circuit breaker открыт и запросы блокируются,
            False если circuit breaker закрыт и запросы разрешены.

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        try:
            result = await self._redis.hgetall(self.key)  # type: ignore[misc]
            data = dict(result) if result else {}
        except Exception as e:
            self.logger.warning(
                f"Ошибка при проверке состояния circuit breaker ({self.key}): {e}",
            )
            return False

        if not data:
            return False

        try:
            failures = int(data.get("failures", "0"))
            last_failed_at = float(data.get("last_failed_at", "0"))
        except (TypeError, ValueError):
            return False

        if failures < self.threshold:
            # Обновляем метрики Prometheus
            try:
                from infra.metrics.prometheus_metrics import CIRCUIT_BREAKER_FAILURES, CIRCUIT_BREAKER_STATE

                CIRCUIT_BREAKER_STATE.labels(key=self.key).set(0.0)
                CIRCUIT_BREAKER_FAILURES.labels(key=self.key).set(float(failures))
            except Exception:
                # Метрики не критичны, игнорируем ошибки
                pass
            return False

        # Окно "покоя" после последней ошибки.
        since_last = self._now() - last_failed_at
        is_open_state = since_last < self.cooldown

        # Обновляем метрики Prometheus
        try:
            from infra.metrics.prometheus_metrics import CIRCUIT_BREAKER_FAILURES, CIRCUIT_BREAKER_STATE

            CIRCUIT_BREAKER_STATE.labels(key=self.key).set(1.0 if is_open_state else 0.0)
            CIRCUIT_BREAKER_FAILURES.labels(key=self.key).set(float(failures))
        except Exception:
            # Метрики не критичны, игнорируем ошибки
            pass

        return is_open_state

    async def record_success(self) -> None:
        """Регистрирует успешный запрос и сбрасывает счётчик ошибок.

        При успешном запросе circuit breaker может быть закрыт, если он был открыт.

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        try:
            await self._redis.hset(self.key, mapping={"failures": "0"})  # type: ignore[misc]
            await self._redis.expire(self.key, self.window)
            self.logger.info(
                f"Circuit breaker {self.key}: успешный запрос зарегистрирован",
                event="circuit_breaker_success",
                status="success",
            )
            # Обновляем метрики Prometheus
            try:
                from infra.metrics.prometheus_metrics import CIRCUIT_BREAKER_FAILURES, CIRCUIT_BREAKER_STATE

                CIRCUIT_BREAKER_STATE.labels(key=self.key).set(0.0)
                CIRCUIT_BREAKER_FAILURES.labels(key=self.key).set(0.0)
            except Exception:
                # Метрики не критичны, игнорируем ошибки
                pass
        except Exception as e:
            self.logger.warning(
                f"Ошибка при регистрации успеха в circuit breaker ({self.key}): {e}",
            )

    async def record_failure(self) -> None:
        """Регистрирует неудачу и обновляет состояние circuit breaker.

        Увеличивает счётчик ошибок и обновляет время последней ошибки.
        Если количество ошибок превышает threshold, circuit-breaker переходит
        в открытое состояние.

        Raises:
            CircuitBreakerOpen: Если circuit breaker открыт после регистрации ошибки.
            redis.RedisError: При ошибке Redis.
        """
        now_ts = self._now()
        mapping = {"last_failed_at": str(now_ts)}

        try:
            failures = await self._redis.hincrby(self.key, "failures", 1)  # type: ignore[misc]
            await self._redis.hset(self.key, mapping=mapping)  # type: ignore[misc]
            await self._redis.expire(self.key, self.window)
            failures = int(failures)

            self.logger.warning(
                f"Circuit breaker {self.key}: ошибка зарегистрирована (failures={failures})",
                event="circuit_breaker_failure",
                status="failure",
            )

            # Обновляем метрики Prometheus
            try:
                from infra.metrics.prometheus_metrics import CIRCUIT_BREAKER_FAILURES

                CIRCUIT_BREAKER_FAILURES.labels(key=self.key).set(float(failures))
            except Exception:
                # Метрики не критичны, игнорируем ошибки
                pass

            # Проверяем, не открылся ли circuit breaker после этой ошибки
            if failures >= self.threshold:
                is_open = await self.is_open()
                if is_open:
                    raise CircuitBreakerOpen(
                        f"Circuit breaker {self.key} открыт после {failures} ошибок",
                    )

        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self.logger.error(
                f"Ошибка при регистрации неудачи в circuit breaker ({self.key}): {e}",
                exc_info=True,
            )

    async def reset(self) -> None:
        """Полностью сбрасывает состояние circuit breaker.

        Удаляет все данные о состоянии circuit breaker из Redis,
        сбрасывая счётчик ошибок и время последней ошибки.

        Raises:
            redis.RedisError: При ошибке Redis.
        """
        try:
            await self._redis.delete(self.key)
        except Exception as e:
            self.logger.warning(
                f"Ошибка при сбросе circuit breaker ({self.key}): {e}",
            )

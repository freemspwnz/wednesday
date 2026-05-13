"""Ошибки доступа к кэшу (application), на которые мапятся сбои Redis-адаптера."""

from __future__ import annotations

from ..base import AppError, UnexpectedAppError


class CacheBackendError(AppError):
    """Базовая ошибка бэкенда кэша с указанием операции."""

    def __init__(self, message: str, *, operation: str) -> None:
        super().__init__(message)
        self.operation = operation


class CacheUnavailableError(CacheBackendError):
    """Кэш временно недоступен (сеть, пул, перегруз Redis)."""


class CacheTimeoutError(CacheBackendError):
    """Операция кэша превысила таймаут сокета/клиента."""


class UnexpectedCacheError(UnexpectedAppError):
    """Неожиданная ошибка Redis, не отнесённая к явным классам выше."""

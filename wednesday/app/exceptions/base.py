"""Модуль ошибок application-слоя."""


class AppError(Exception):
    """Базовый класс для всех ошибок application-слоя."""


class UnexpectedAppError(AppError):
    """Unexpected application error."""

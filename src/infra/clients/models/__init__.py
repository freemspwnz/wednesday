"""Модели для типизации Request/Response структур HTTP-клиентов."""

from infra.clients.models.gigachat import (
    GigaChatChoice,
    GigaChatCompletionResponse,
    GigaChatMessage,
    GigaChatModelInfo,
    GigaChatModelsListResponse,
    GigaChatTokenResponse,
)
from infra.clients.models.kandinsky import (
    KandinskyGenerationParams,
    KandinskyGenerationRequest,
    KandinskyGenerationStartResponse,
    KandinskyPipelineResponse,
    KandinskyResult,
    KandinskyStatus,
    KandinskyStatusResponse,
)
from shared.models import APIStatusResult, SetModelResult

__all__ = [
    "APIStatusResult",
    "GigaChatChoice",
    "GigaChatCompletionResponse",
    "GigaChatMessage",
    "GigaChatModelInfo",
    "GigaChatModelsListResponse",
    "GigaChatTokenResponse",
    "KandinskyGenerationParams",
    "KandinskyGenerationRequest",
    "KandinskyGenerationStartResponse",
    "KandinskyPipelineResponse",
    "KandinskyResult",
    "KandinskyStatus",
    "KandinskyStatusResponse",
    "SetModelResult",
]

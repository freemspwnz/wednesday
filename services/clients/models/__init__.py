"""Модели для типизации Request/Response структур HTTP-клиентов."""

from services.clients.models.gigachat import (
    GigaChatChoice,
    GigaChatCompletionResponse,
    GigaChatMessage,
    GigaChatModelInfo,
    GigaChatModelsListResponse,
    GigaChatTokenResponse,
)
from services.clients.models.kandinsky import (
    KandinskyGenerationParams,
    KandinskyGenerationRequest,
    KandinskyGenerationStartResponse,
    KandinskyPipelineResponse,
    KandinskyResult,
    KandinskyStatus,
    KandinskyStatusResponse,
)
from services.clients.models.status import (
    APIStatusResult,
    SetModelResult,
)

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

"""Pydantic модели для Kandinsky API.

Модели для типизации и валидации Request/Response структур API Kandinsky (Fusion Brain).
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class KandinskyPipelineResponse(BaseModel):
    """Ответ API при получении списка pipelines (моделей)."""

    id: str
    name: str

    class Config:
        populate_by_name = True  # Поддержка и camelCase и snake_case


class KandinskyGenerationParams(BaseModel):
    """Параметры генерации изображения."""

    query: str = Field(..., description="Промпт для генерации")

    class Config:
        populate_by_name = True


class KandinskyGenerationRequest(BaseModel):
    """Запрос на генерацию изображения."""

    type: str = Field(default="GENERATE", description="Тип запроса")
    numImages: int = Field(default=1, description="Количество изображений", alias="numImages")
    width: int = Field(default=1024, description="Ширина изображения")
    height: int = Field(default=1024, description="Высота изображения")
    generateParams: KandinskyGenerationParams = Field(..., alias="generateParams")

    class Config:
        populate_by_name = True


class KandinskyStatus(StrEnum):
    """Статусы генерации изображения."""

    DONE = "DONE"
    FAIL = "FAIL"
    INITIAL = "INITIAL"
    PROCESSING = "PROCESSING"


class KandinskyGenerationStartResponse(BaseModel):
    """Ответ API при запуске генерации."""

    uuid: str = Field(..., description="UUID задачи генерации")

    class Config:
        populate_by_name = True


class KandinskyResult(BaseModel):
    """Результат генерации изображения."""

    files: list[str] = Field(..., description="Список base64-закодированных изображений")

    class Config:
        populate_by_name = True


class KandinskyStatusResponse(BaseModel):
    """Ответ API при проверке статуса генерации."""

    status: KandinskyStatus = Field(..., description="Статус генерации")
    result: KandinskyResult | None = Field(None, description="Результат генерации (если DONE)")
    errorDescription: str | None = Field(None, alias="errorDescription", description="Описание ошибки (если FAIL)")

    class Config:
        populate_by_name = True

"""Pydantic модели для GigaChat API.

Модели для типизации и валидации Request/Response структур API GigaChat.
"""

from pydantic import BaseModel, Field


class GigaChatTokenResponse(BaseModel):
    """Ответ API при получении access token."""

    access_token: str = Field(..., description="Access token для аутентификации")
    expires_in: int = Field(default=1800, description="Время жизни токена в секундах")

    class Config:
        populate_by_name = True


class GigaChatMessage(BaseModel):
    """Сообщение в чате."""

    role: str = Field(..., description="Роль отправителя (system, user, assistant)")
    content: str = Field(..., description="Содержимое сообщения")

    class Config:
        populate_by_name = True


class GigaChatChoice(BaseModel):
    """Вариант ответа от API."""

    message: GigaChatMessage = Field(..., description="Сообщение от ассистента")

    class Config:
        populate_by_name = True


class GigaChatCompletionResponse(BaseModel):
    """Ответ API при генерации промпта (chat completion)."""

    choices: list[GigaChatChoice] = Field(..., description="Список вариантов ответа")

    class Config:
        populate_by_name = True


class GigaChatModelInfo(BaseModel):
    """Информация о модели GigaChat."""

    id: str | None = Field(None, description="ID модели")
    name: str | None = Field(None, description="Название модели")
    model: str | None = Field(None, description="Имя модели (альтернативное поле)")

    class Config:
        populate_by_name = True

    def get_model_name(self) -> str | None:
        """Возвращает имя модели из любого доступного поля."""
        return self.id or self.name or self.model


class GigaChatModelsListResponse(BaseModel):
    """Ответ API при получении списка моделей (может быть dict с data/models)."""

    data: list[GigaChatModelInfo] | None = Field(None, description="Модели в поле data")
    models: list[GigaChatModelInfo] | None = Field(None, description="Модели в поле models")

    class Config:
        populate_by_name = True

    def get_models_list(self) -> list[GigaChatModelInfo]:
        """Возвращает список моделей из любого доступного поля."""
        if self.data:
            return self.data
        if self.models:
            return self.models
        return []

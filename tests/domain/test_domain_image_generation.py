"""Unit-тесты для ImageGenerationService."""

from __future__ import annotations

import pytest

from domain.image_generation import ImageGenerationService
from domain.value_objects import MAX_PROMPT_LENGTH, MIN_PROMPT_LENGTH, Prompt
from shared.base.exceptions import ImageGenerationError
from shared.models import APIStatusResult, SetModelResult
from shared.protocols import ITextToImageClient


class MockImageClient(ITextToImageClient):
    """Мок клиента для генерации изображений."""

    def __init__(self, response: bytes = b"mock-image-data") -> None:
        self.response = response
        self.calls: list[tuple[str, str | None]] = []

    async def generate(self, prompt: str, user_id: str | None = None) -> bytes:
        """Сохраняет вызов и возвращает настроенный ответ."""
        self.calls.append((prompt, user_id))
        return self.response

    async def check_api_status(self, save_models: bool = True) -> APIStatusResult:
        """Мок метода check_api_status."""
        return APIStatusResult.success(
            message="ok",
            models=[],
            current_model_id=None,
            current_model_name=None,
        )

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Мок метода get_available_models."""
        return []

    async def set_model(self, model_identifier: str) -> SetModelResult:
        """Мок метода set_model."""
        return SetModelResult.ok("ok")


class TestPromptNormalize:
    """Тесты для метода _normalize в Value Object Prompt."""

    def test_removes_trailing_whitespace(self) -> None:
        """Тест на удаление пробелов по краям."""
        result = Prompt._normalize("  test prompt  ")
        assert result == "test prompt"

    def test_removes_extra_spaces_inside(self) -> None:
        """Тест на удаление лишних пробелов внутри текста."""
        result = Prompt._normalize("test    prompt   with    spaces")
        assert result == "test prompt with spaces"

    def test_handles_empty_string_after_strip(self) -> None:
        """Тест на обработку пустой строки после strip."""
        result = Prompt._normalize("   ")
        assert result == ""

    def test_preserves_single_space(self) -> None:
        """Тест на сохранение одного пробела между словами."""
        result = Prompt._normalize("test prompt")
        assert result == "test prompt"

    def test_handles_newlines_and_tabs(self) -> None:
        """Тест на обработку переносов строк и табуляций."""
        result = Prompt._normalize("test\tprompt\nwith\n\tnewlines")
        assert result == "test prompt with newlines"


class TestPromptValidation:
    """Тесты для валидации в Value Object Prompt."""

    def test_raises_on_empty_prompt(self) -> None:
        """Тест на пустой промпт должен выбрасывать ValueError."""
        with pytest.raises(ValueError, match="Промпт не может быть пустым"):
            Prompt("")

    def test_raises_on_too_short_prompt(self) -> None:
        """Тест на промпт короче MIN_PROMPT_LENGTH должен выбрасывать ValueError."""
        # MIN_PROMPT_LENGTH = 1, поэтому пустая строка уже проверена выше
        # Но если MIN_PROMPT_LENGTH будет больше 1, это проверит такой случай
        if MIN_PROMPT_LENGTH > 1:
            with pytest.raises(ValueError, match="слишком короткий"):
                Prompt("a" * (MIN_PROMPT_LENGTH - 1))

    def test_raises_on_too_long_prompt(self) -> None:
        """Тест на промпт длиннее MAX_PROMPT_LENGTH должен выбрасывать ValueError."""
        long_prompt = "a" * (MAX_PROMPT_LENGTH + 1)
        with pytest.raises(ValueError, match="слишком длинный"):
            Prompt(long_prompt)

    def test_accepts_valid_prompt(self) -> None:
        """Тест на валидный промпт не должен выбрасывать исключение."""
        valid_prompt = "a" * MIN_PROMPT_LENGTH
        # Не должно быть исключения
        prompt = Prompt(valid_prompt)
        assert prompt.value == valid_prompt

    def test_accepts_max_length_prompt(self) -> None:
        """Тест на промпт максимальной длины должен быть валидным."""
        max_prompt = "a" * MAX_PROMPT_LENGTH
        # Не должно быть исключения
        prompt = Prompt(max_prompt)
        assert prompt.value == max_prompt

    def test_normalizes_prompt_on_creation(self) -> None:
        """Тест на нормализацию промпта при создании."""
        prompt = Prompt("  test   prompt  ")
        assert prompt.value == "test prompt"


class TestGenerate:
    """Тесты для метода generate."""

    @pytest.mark.asyncio
    async def test_uses_normalized_prompt_for_client_call(self) -> None:
        """Тест на использование нормализованного промпта при вызове клиента."""
        mock_client = MockImageClient()
        service = ImageGenerationService(mock_client)

        await service.generate("  test   prompt  ", user_id=42)

        # Проверяем, что клиент вызван с нормализованным промптом
        assert len(mock_client.calls) == 1
        assert mock_client.calls[0][0] == "test prompt"
        assert mock_client.calls[0][1] == "42"

    @pytest.mark.asyncio
    async def test_raises_image_generation_error_on_invalid_prompt(self) -> None:
        """Тест на выбрасывание ImageGenerationError при невалидном промпте."""
        mock_client = MockImageClient()
        service = ImageGenerationService(mock_client)

        with pytest.raises(ImageGenerationError, match="Невалидный промпт"):
            await service.generate("")

        # Клиент не должен быть вызван
        assert len(mock_client.calls) == 0

    @pytest.mark.asyncio
    async def test_raises_on_too_long_prompt(self) -> None:
        """Тест на выбрасывание ImageGenerationError при слишком длинном промпте."""
        mock_client = MockImageClient()
        service = ImageGenerationService(mock_client)

        long_prompt = "a" * (MAX_PROMPT_LENGTH + 1)
        with pytest.raises(ImageGenerationError, match="Невалидный промпт"):
            await service.generate(long_prompt)

        # Клиент не должен быть вызван
        assert len(mock_client.calls) == 0

    @pytest.mark.asyncio
    async def test_successful_generation_with_valid_prompt(self) -> None:
        """Тест на успешную генерацию с валидным промптом."""
        mock_client = MockImageClient(response=b"image-data")
        service = ImageGenerationService(mock_client)

        result = await service.generate("valid prompt", user_id=123)

        assert result == b"image-data"
        assert len(mock_client.calls) == 1
        assert mock_client.calls[0][0] == "valid prompt"
        assert mock_client.calls[0][1] == "123"

    @pytest.mark.asyncio
    async def test_raises_exception_when_client_raises_exception(self) -> None:
        """Тест на проброс исключения, когда клиент пробрасывает исключение."""
        from infra.clients.exceptions import APIError

        class FailingMockClient(ITextToImageClient):
            async def generate(self, prompt: str, user_id: str | None = None) -> bytes:
                raise APIError("Test error", status_code=500)

            async def check_api_status(self, save_models: bool = True) -> APIStatusResult:
                return APIStatusResult.success(
                    message="Error",
                    models=[],
                    current_model_id=None,
                    current_model_name=None,
                )

            async def get_available_models(self, save_models: bool = True) -> list[str]:
                return []

            async def set_model(self, model_identifier: str) -> SetModelResult:
                return SetModelResult.error("Error")

        mock_client = FailingMockClient()
        service = ImageGenerationService(mock_client)

        with pytest.raises(ImageGenerationError):
            await service.generate("valid prompt")

    @pytest.mark.asyncio
    async def test_normalizes_prompt_before_validation(self) -> None:
        """Тест на нормализацию промпта перед валидацией (пустая строка после strip)."""
        mock_client = MockImageClient()
        service = ImageGenerationService(mock_client)

        with pytest.raises(ImageGenerationError, match="Невалидный промпт"):
            await service.generate("   ")

        # Клиент не должен быть вызван
        assert len(mock_client.calls) == 0

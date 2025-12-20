"""Unit-тесты для ImageGenerationService."""

from __future__ import annotations

import pytest

from services.base.exceptions import ImageGenerationError
from services.domain.image_generation import (
    MAX_PROMPT_LENGTH,
    MIN_PROMPT_LENGTH,
    ImageGenerationService,
)
from services.protocols import ITextToImageClient


class MockImageClient(ITextToImageClient):
    """Мок клиента для генерации изображений."""

    def __init__(self, response: bytes | None = b"mock-image-data") -> None:
        self.response = response
        self.calls: list[tuple[str, str | None]] = []

    async def generate(self, prompt: str, user_id: str | None = None) -> bytes | None:
        """Сохраняет вызов и возвращает настроенный ответ."""
        self.calls.append((prompt, user_id))
        return self.response

    async def check_api_status(
        self, save_models: bool = True
    ) -> tuple[bool, str, list[str], tuple[str | None, str | None]]:
        """Мок метода check_api_status."""
        return (True, "ok", [], (None, None))

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Мок метода get_available_models."""
        return []

    async def set_model(self, model_identifier: str) -> tuple[bool, str]:
        """Мок метода set_model."""
        return (True, "ok")


class TestNormalizePrompt:
    """Тесты для метода _normalize_prompt."""

    def test_removes_trailing_whitespace(self) -> None:
        """Тест на удаление пробелов по краям."""
        result = ImageGenerationService._normalize_prompt("  test prompt  ")
        assert result == "test prompt"

    def test_removes_extra_spaces_inside(self) -> None:
        """Тест на удаление лишних пробелов внутри текста."""
        result = ImageGenerationService._normalize_prompt("test    prompt   with    spaces")
        assert result == "test prompt with spaces"

    def test_handles_empty_string_after_strip(self) -> None:
        """Тест на обработку пустой строки после strip."""
        result = ImageGenerationService._normalize_prompt("   ")
        assert result == ""

    def test_preserves_single_space(self) -> None:
        """Тест на сохранение одного пробела между словами."""
        result = ImageGenerationService._normalize_prompt("test prompt")
        assert result == "test prompt"

    def test_handles_newlines_and_tabs(self) -> None:
        """Тест на обработку переносов строк и табуляций."""
        result = ImageGenerationService._normalize_prompt("test\tprompt\nwith\n\tnewlines")
        assert result == "test prompt with newlines"


class TestValidatePrompt:
    """Тесты для метода _validate_prompt."""

    def test_raises_on_empty_prompt(self) -> None:
        """Тест на пустой промпт должен выбрасывать ValueError."""
        with pytest.raises(ValueError, match="Промпт не может быть пустым"):
            ImageGenerationService._validate_prompt("")

    def test_raises_on_too_short_prompt(self) -> None:
        """Тест на промпт короче MIN_PROMPT_LENGTH должен выбрасывать ValueError."""
        # MIN_PROMPT_LENGTH = 1, поэтому пустая строка уже проверена выше
        # Но если MIN_PROMPT_LENGTH будет больше 1, это проверит такой случай
        if MIN_PROMPT_LENGTH > 1:
            with pytest.raises(ValueError, match="слишком короткий"):
                ImageGenerationService._validate_prompt("a" * (MIN_PROMPT_LENGTH - 1))

    def test_raises_on_too_long_prompt(self) -> None:
        """Тест на промпт длиннее MAX_PROMPT_LENGTH должен выбрасывать ValueError."""
        long_prompt = "a" * (MAX_PROMPT_LENGTH + 1)
        with pytest.raises(ValueError, match="слишком длинный"):
            ImageGenerationService._validate_prompt(long_prompt)

    def test_accepts_valid_prompt(self) -> None:
        """Тест на валидный промпт не должен выбрасывать исключение."""
        valid_prompt = "a" * MIN_PROMPT_LENGTH
        # Не должно быть исключения
        ImageGenerationService._validate_prompt(valid_prompt)

    def test_accepts_max_length_prompt(self) -> None:
        """Тест на промпт максимальной длины должен быть валидным."""
        max_prompt = "a" * MAX_PROMPT_LENGTH
        # Не должно быть исключения
        ImageGenerationService._validate_prompt(max_prompt)


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
    async def test_returns_none_when_client_returns_none(self) -> None:
        """Тест на возврат None, когда клиент возвращает None."""
        mock_client = MockImageClient(response=None)
        service = ImageGenerationService(mock_client)

        result = await service.generate("valid prompt")

        assert result is None
        assert len(mock_client.calls) == 1

    @pytest.mark.asyncio
    async def test_normalizes_prompt_before_validation(self) -> None:
        """Тест на нормализацию промпта перед валидацией (пустая строка после strip)."""
        mock_client = MockImageClient()
        service = ImageGenerationService(mock_client)

        with pytest.raises(ImageGenerationError, match="Невалидный промпт"):
            await service.generate("   ")

        # Клиент не должен быть вызван
        assert len(mock_client.calls) == 0

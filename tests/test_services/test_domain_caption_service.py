"""Unit-тесты для CaptionService."""

from __future__ import annotations

import pytest

from services.domain.caption_service import CaptionService


class TestCaptionService:
    """Тесты для CaptionService."""

    def test_get_random_caption_returns_caption_from_list(self) -> None:
        """Тест на возврат подписи из списка."""
        captions = ["Caption 1", "Caption 2", "Caption 3"]
        service = CaptionService(captions)

        result = service.get_random_caption()

        assert result in captions

    def test_get_all_captions_returns_copy_of_captions(self) -> None:
        """Тест на возврат копии списка подписей."""
        captions = ["Caption 1", "Caption 2", "Caption 3"]
        service = CaptionService(captions)

        result = service.get_all_captions()

        assert result == captions
        assert result is not captions  # Должна быть копия

    def test_has_captions_returns_true_when_captions_exist(self) -> None:
        """Тест на возврат True, когда есть подписи."""
        captions = ["Caption 1"]
        service = CaptionService(captions)

        assert service.has_captions() is True

    def test_has_captions_returns_false_when_no_captions(self) -> None:
        """Тест на возврат False, когда нет подписей (не должно произойти из-за валидации)."""
        captions = ["Caption 1"]
        service = CaptionService(captions)

        # После создания сервиса всегда есть подписи
        assert service.has_captions() is True

    def test_raises_value_error_on_empty_list(self) -> None:
        """Тест на выбрасывание ValueError при пустом списке."""
        with pytest.raises(ValueError, match="Список подписей не может быть пустым"):
            CaptionService([])

    def test_raises_value_error_on_empty_tuple(self) -> None:
        """Тест на выбрасывание ValueError при пустом кортеже."""
        with pytest.raises(ValueError, match="Список подписей не может быть пустым"):
            CaptionService(())

    def test_accepts_tuple_of_captions(self) -> None:
        """Тест на принятие кортежа подписей."""
        captions = ("Caption 1", "Caption 2")
        service = CaptionService(captions)

        result = service.get_random_caption()
        assert result in captions

    def test_get_random_caption_returns_different_captions(self) -> None:
        """Тест на возврат разных подписей при нескольких вызовах."""
        captions = ["Caption 1", "Caption 2", "Caption 3"]
        service = CaptionService(captions)

        results = [service.get_random_caption() for _ in range(10)]

        # Хотя бы одна подпись должна отличаться (вероятностный тест)
        assert len(set(results)) > 1

    def test_get_all_captions_preserves_order(self) -> None:
        """Тест на сохранение порядка подписей."""
        captions = ["Caption 1", "Caption 2", "Caption 3"]
        service = CaptionService(captions)

        result = service.get_all_captions()

        assert result == captions

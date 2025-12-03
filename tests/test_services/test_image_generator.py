from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.clients.image_client_container import ImageClientContainer
from services.image_generator import ImageGenerator
from tests._doubles.clients import MockTextToImageClient, MockTextToTextClient
from utils.images_store import ImagesStore
from utils.postgres_client import get_postgres_pool
from utils.prompts_store import PromptsStore


@pytest.mark.asyncio
async def test_check_api_status_dry_run(monkeypatch: Any) -> None:
    """Dry-run: проверяем, что возвращается ожидаемый статус без настоящих запросов."""

    from services.clients.kandinsky import KandinskyClient

    generator = ImageGenerator(
        image_client=MockTextToImageClient(),
        text_client=MockTextToTextClient(),
    )
    # Используем настоящий KandinskyClient, но подменяем его метод, чтобы исключить реальные HTTP‑запросы.
    kandinsky_client = KandinskyClient()
    monkeypatch.setattr(
        kandinsky_client,
        "check_api_status",
        AsyncMock(
            return_value=(True, "✅ API доступен, ключ валиден", ["Model One (ID: p1)"], (None, None)),
        ),
    )
    generator._kandinsky_client = kandinsky_client
    ok, message, models, current = await generator.check_api_status()

    assert ok is True
    assert "доступен" in message
    assert models
    assert current == (None, None)


def test_save_image_locally_success(tmp_path: Path) -> None:
    generator = ImageGenerator(
        image_client=MockTextToImageClient(),
        text_client=MockTextToTextClient(),
    )
    data = b"fake-image"

    saved = generator.save_image_locally(data, folder=str(tmp_path), prefix="frog", max_files=1)

    assert saved
    saved_path = Path(saved)
    assert saved_path.exists()
    assert saved_path.read_bytes() == data


def test_save_image_locally_handles_error(monkeypatch: Any) -> None:
    generator = ImageGenerator(
        image_client=MockTextToImageClient(),
        text_client=MockTextToTextClient(),
    )
    target_folder = "/tmp/forbidden"

    def fail_write_bytes(self: Any, data: bytes) -> None:
        raise OSError("write error")

    monkeypatch.setattr("services.image_generator.Path.write_bytes", fail_write_bytes, raising=False)

    assert generator.save_image_locally(b"data", folder=target_folder) == ""


@pytest.mark.asyncio
async def test_generate_frog_image_success(monkeypatch: Any) -> None:
    # Создаём мок с правильным ответом и новый контейнер для каждого теста
    image_client = MockTextToImageClient(generate_response=b"img")
    container = ImageClientContainer()
    container.set_initial_client(image_client)
    generator = ImageGenerator(
        image_client=container,
        text_client=MockTextToTextClient(),
    )

    def fake_generate_prompt() -> str:
        return "frog prompt"

    monkeypatch.setattr(generator, "_generate_prompt", AsyncMock(side_effect=fake_generate_prompt))
    monkeypatch.setattr(generator, "_get_fallback_prompt", MagicMock(return_value="fallback prompt"))

    result = await generator.generate_frog_image(user_id=42)

    assert result is not None
    image, caption = result
    assert image == b"img"
    assert caption in generator.captions


@pytest.mark.asyncio
async def test_generate_frog_image_uses_cache_on_existing_prompt_hash(monkeypatch: Any, cleanup_tables: Any) -> None:
    """
    При повторном запросе с тем же prompt_hash генератор должен использовать кеш из таблицы images,
    а не вызывать живую генерацию второй раз.
    """

    # Создаём мок с правильным ответом и новый контейнер для каждого теста
    image_client = MockTextToImageClient(generate_response=b"cached-image-bytes")
    container = ImageClientContainer()
    container.set_initial_client(image_client)
    generator = ImageGenerator(
        image_client=container,
        text_client=MockTextToTextClient(),
    )

    prompt_text = "cached frog prompt"

    def fake_generate_prompt() -> str:
        return prompt_text

    monkeypatch.setattr(generator, "_generate_prompt", AsyncMock(side_effect=fake_generate_prompt))
    monkeypatch.setattr(generator, "_get_fallback_prompt", MagicMock(return_value=prompt_text))

    # Первый вызов — создаёт промпт и изображение, записывает их в БД.
    result1 = await generator.generate_frog_image(user_id=123)
    assert result1 is not None
    img1, caption1 = result1
    assert img1 == b"cached-image-bytes"
    assert isinstance(caption1, str)

    # Второй вызов с тем же промптом должен взять кеш.
    result2 = await generator.generate_frog_image(user_id=123)
    assert result2 is not None
    img2, caption2 = result2
    assert img2 == b"cached-image-bytes"
    assert isinstance(caption2, str)

    # Генерация должна была произойти ровно один раз.
    assert len(image_client.calls) == 1

    # В БД должна быть одна запись для этого prompt_hash.
    prompts_store = PromptsStore()
    prompt_record = await prompts_store.get_or_create_prompt(prompt_text)
    images_store = ImagesStore()
    image_record = await images_store.get_by_prompt_hash(prompt_record.prompt_hash)
    assert image_record is not None


@pytest.mark.asyncio
async def test_generate_frog_image_network_error(monkeypatch: Any) -> None:
    # Создаём мок и новый контейнер для каждого теста
    image_client = MockTextToImageClient()
    container = ImageClientContainer()
    container.set_initial_client(image_client)
    generator = ImageGenerator(
        image_client=container,
        text_client=MockTextToTextClient(),
    )

    monkeypatch.setattr(generator, "_generate_prompt", AsyncMock(return_value="frog prompt"))
    # Патчим underlying клиент в контейнере
    underlying = container.get_client()
    assert underlying is not None
    monkeypatch.setattr(underlying, "generate", AsyncMock(side_effect=Exception("network")))

    result = await generator.generate_frog_image(user_id=777)

    assert result is None


def test_get_random_caption() -> None:
    generator = ImageGenerator(
        image_client=MockTextToImageClient(),
        text_client=MockTextToTextClient(),
    )
    caption = generator.get_random_caption()
    assert caption
    assert isinstance(caption, str)
    assert caption in generator.captions


def test_get_fallback_prompt() -> None:
    from services.image_generator import ImageGenerator

    prompt = ImageGenerator._get_fallback_prompt()
    assert prompt
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_get_random_saved_image_no_files(tmp_path: Path) -> None:
    generator = ImageGenerator(
        image_client=MockTextToImageClient(),
        text_client=MockTextToTextClient(),
    )
    result = generator.get_random_saved_image(folder=str(tmp_path))
    assert result is None


def test_get_random_saved_image_with_files(tmp_path: Path) -> None:
    generator = ImageGenerator(
        image_client=MockTextToImageClient(),
        text_client=MockTextToTextClient(),
    )
    # Создаём тестовые файлы изображений
    (tmp_path / "frog_20251101_120000.png").write_bytes(b"fake image 1")
    (tmp_path / "frog_20251102_120000.png").write_bytes(b"fake image 2")

    result = generator.get_random_saved_image(folder=str(tmp_path))
    assert result is not None
    image_data, caption = result
    assert image_data in {b"fake image 1", b"fake image 2"}
    assert isinstance(caption, str)


@pytest.mark.asyncio
async def test_set_model_success(monkeypatch: Any, cleanup_tables: Any) -> None:
    # Создаём мок и новый контейнер для каждого теста
    mock_client = MockTextToImageClient(
        set_model_response=(True, "Модель установлена: Model One (ID: p1)"),
    )
    container = ImageClientContainer()
    container.set_initial_client(mock_client)

    generator = ImageGenerator(
        image_client=container,
        text_client=MockTextToTextClient(),
    )

    success, message = await generator.image_client.set_model("p1")
    assert success is True
    assert "установлена" in message.lower() or "успешно" in message.lower()


@pytest.mark.asyncio
async def test_set_model_not_found(monkeypatch: Any) -> None:
    # Создаём мок с правильным ответом и новый контейнер для каждого теста
    mock_client = MockTextToImageClient(
        set_model_response=(False, "Модель 'nonexistent' не найдена"),
    )
    container = ImageClientContainer()
    container.set_initial_client(mock_client)

    generator = ImageGenerator(
        image_client=container,
        text_client=MockTextToTextClient(),
    )

    # Используем image_client напрямую (контейнер проксирует к моку)
    success, message = await generator.image_client.set_model("nonexistent")
    assert success is False
    assert "не найдена" in message.lower() or "не найдено" in message.lower()


@pytest.mark.asyncio
async def test_generate_frog_image_records_metrics_events_success(monkeypatch: Any, cleanup_tables: Any) -> None:
    """
    При успешной генерации должны записываться как минимум два события:
    - generation/started
    - generation/ok с ненулевой latency и заполненными hash.
    """

    # Создаём мок с правильным ответом и новый контейнер для каждого теста
    image_client = MockTextToImageClient(generate_response=b"img-metrics")
    container = ImageClientContainer()
    container.set_initial_client(image_client)
    generator = ImageGenerator(
        image_client=container,
        text_client=MockTextToTextClient(),
    )

    prompt_text = "metrics frog prompt"

    def fake_generate_prompt() -> str:
        return prompt_text

    monkeypatch.setattr(generator, "_generate_prompt", AsyncMock(side_effect=fake_generate_prompt))
    monkeypatch.setattr(generator, "_get_fallback_prompt", MagicMock(return_value=prompt_text))

    result = await generator.generate_frog_image(user_id=999)
    assert result is not None

    pool = get_postgres_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT event_type, status, prompt_hash, image_hash, latency_ms, user_id "
            "FROM metrics_events ORDER BY id ASC;",
        )

    # Должно быть как минимум два события.
    MIN_EXPECTED_EVENTS = 2
    assert len(rows) >= MIN_EXPECTED_EVENTS

    started = rows[0]
    completed = rows[-1]

    assert started["event_type"] == "generation"
    assert started["status"] == "started"
    assert started["prompt_hash"] is not None
    # user_id хранится как текст
    assert started["user_id"] == "999"

    assert completed["event_type"] == "generation"
    assert completed["status"] == "ok"
    assert completed["prompt_hash"] is not None
    assert completed["image_hash"] is not None
    assert completed["latency_ms"] is not None


@pytest.mark.asyncio
async def test_generate_frog_image_records_cache_hit(monkeypatch: Any, cleanup_tables: Any) -> None:
    """
    При cache hit должно писаться событие cache_hit с latency_ms=0 и status='cached'.
    """

    # Создаём мок с правильным ответом и новый контейнер для каждого теста
    image_client = MockTextToImageClient(generate_response=b"cached-bytes")
    container = ImageClientContainer()
    container.set_initial_client(image_client)
    generator = ImageGenerator(
        image_client=container,
        text_client=MockTextToTextClient(),
    )

    prompt_text = "cached metrics frog"

    def fake_generate_prompt() -> str:
        return prompt_text

    monkeypatch.setattr(generator, "_generate_prompt", AsyncMock(side_effect=fake_generate_prompt))
    monkeypatch.setattr(generator, "_get_fallback_prompt", MagicMock(return_value=prompt_text))

    # Первый вызов создаёт запись и изображение.
    result1 = await generator.generate_frog_image(user_id=1)
    assert result1 is not None

    # Очищаем события, чтобы зафиксировать только cache_hit.
    pool = get_postgres_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE metrics_events RESTART IDENTITY;")

    # Второй вызов должен использовать кеш и записать cache_hit.
    result2 = await generator.generate_frog_image(user_id=1)
    assert result2 is not None

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT event_type, status, latency_ms FROM metrics_events ORDER BY id ASC;",
        )

    # Должен быть хотя бы один cache_hit
    cache_hits = [r for r in rows if r["event_type"] == "cache_hit"]
    assert cache_hits, f"metrics_events rows={rows!r}"
    hit = cache_hits[0]
    assert hit["status"] == "cached"
    assert hit["latency_ms"] == 0


@pytest.mark.asyncio
async def test_generate_frog_image_records_error_on_exception(monkeypatch: Any, cleanup_tables: Any) -> None:
    """
    При ошибке генерации должно писаться событие error.
    """

    # Создаём мок и новый контейнер для каждого теста
    image_client = MockTextToImageClient()
    container = ImageClientContainer()
    container.set_initial_client(image_client)
    generator = ImageGenerator(
        image_client=container,
        text_client=MockTextToTextClient(),
    )

    def fake_generate_prompt() -> str:
        return "error frog prompt"

    monkeypatch.setattr(generator, "_generate_prompt", AsyncMock(side_effect=fake_generate_prompt))
    monkeypatch.setattr(generator, "_get_fallback_prompt", MagicMock(return_value="error frog prompt"))
    # Патчим underlying клиент в контейнере
    underlying = container.get_client()
    assert underlying is not None
    monkeypatch.setattr(underlying, "generate", AsyncMock(side_effect=RuntimeError("boom")))

    result = await generator.generate_frog_image(user_id=555)
    assert result is None

    pool = get_postgres_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT event_type, status, user_id FROM metrics_events ORDER BY id ASC;",
        )

    errors = [r for r in rows if r["event_type"] == "error"]
    assert errors, f"metrics_events rows={rows!r}"
    # Проверяем, что хотя бы одно событие ошибки относится к нашему пользователю.
    assert any(e["user_id"] == "555" for e in errors)

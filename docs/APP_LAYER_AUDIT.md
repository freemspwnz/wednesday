## Аудит слоя `app/`

**Дата:** 2025-12-22  
**Аудитор:** GPT-5.1 (AI Assistant в Cursor)  
**Область:** `src/app/` (`dispatch_service.py`, `dispatch_execution_service.py`, `database_operations_service.py`,  
`image_service.py`, `fallback_service.py`, `prompt_service.py`, `target_preparation_service.py`,  
`admin_dashboard_service.py`, `admin_dashboard_builders.py`, `api_status_service.py`,  
`frog_limit_service.py`, `frog_requests.py`, `dispatch_result.py`, `__init__.py`)

---

## 1. Резюме

- **Общая оценка архитектурной чистоты слоя `app/`:** **8/10**
- **Сильные стороны:**
  - **Чистая граница с `bot/`:** в `app/` нет импортов из `bot/`, Telegram‑типы (`Update`, `Message`, `CallbackQuery`) в слой не протекают; взаимодействие идёт через абстрактные коллбеки и протоколы.
  - **Систематическое использование протоколов:** почти все зависимости приходят как интерфейсы из `shared.protocols` или доменные сервисы из `domain/`.
  - **Хорошая декомпозиция координаторов:** отдельные сервисы для таргетов, выполнения рассылки, fallback‑ов, генерации промптов/изображений, админ‑дашборда, rate limiting и постановки задач в очередь.
  - **Типизация и DTO:** повсюду используются type hints (Python 3.10+), `TypedDict` (`DispatchResult`) и `@dataclass`‑DTO для дашборда.
- **Зоны риска:**
  - **Лик слоя в `infra/` внутри `DatabaseOperationsService`:** прямые импорты `infra.database.*` и `infra.logging.*` в application‑сервисе при отсутствии фабрики UoW.
  - **Широкие `except Exception` в координаторах:** местами скрывают программные ошибки и усложняют диагностику.
  - **Дублирующаяся логика отправки и регистрации dispatch‑ов между `DispatchExecutionService` и `FallbackService`.**

---

## 2. Архитектурная целостность и паттерны

### 2.1 Утечки слоёв и зависимости

- **Границы `app/ → bot/`:**
  - В файлах `src/app/*.py` **нет** импортов из `bot.*`.
  - Взаимодействие с Telegram реализовано через:
    - коллбеки (`Callable[[...], Awaitable[...]]`) в `DispatchService`, `DispatchExecutionService`, `FallbackService`, `TargetPreparationService`;
    - абстрактный `ITaskQueue` в `FrogRequestService`;
    - протоколы `IMessagingService` вообще не используются в `app/`, вместо этого слой остаётся на уровне «отправь картинку через переданную функцию».
  - **Вывод:** ограничение *«app не зависит от bot»* выдержано.

- **Границы `app/ → infra/`:**
  - Большинство сервисов зависят только от:
    - доменных сервисов (`domain.image_generation.ImageGenerationService`, `domain.caption_service.CaptionService`, `domain.prompt_generation.PromptGenerationService`);
    - протоколов из `shared.protocols` (`ICache`, `IMetrics`, `ICircuitBreaker`, `IImageStorageUnitOfWork`, `IDatabaseUnitOfWork`, `IChatsRepo`, `IUsageTracker`, `IDispatchRegistry`, `IModelsRepo`, `IRateLimiter`, `ITaskQueue`, `ITextToImageClient`, `ITextToTextClient`);
    - базового класса `BaseService` и исключений из `shared.base`.
  - **Исключение (критично):** `DatabaseOperationsService.record_dispatch_success`:

```48:76:src/app/database_operations_service.py
        if self._unit_of_work_factory is None:
            # Fallback для обратной совместимости (breaking change - будет удалено)
            from infra.database.database_unit_of_work import DatabaseUnitOfWork
            from infra.database.postgres_client import get_postgres_pool
            from infra.logging.logger import get_logger

            def create_uow() -> IDatabaseUnitOfWork:
                logger = get_logger(DatabaseUnitOfWork.__name__)
                return DatabaseUnitOfWork(pool=get_postgres_pool(), logger=logger)

            uow: IDatabaseUnitOfWork = create_uow()
        else:
            uow = self._unit_of_work_factory()
```

  - Здесь application‑сервис:
    - напрямую импортирует конкретные классы/функции из `infra.database` и `infra.logging`;
    - сам строит `DatabaseUnitOfWork` и логгер;
    - тем самым **ломает принцип инверсии зависимостей** и усложняет тестирование/подмену реализации.

  - **Вывод:** за исключением этого участка, слой `app/` держит границу с `infra/` через протоколы; **данный fallback — главный архитектурный дефект**.

### 2.2 Dependency Injection (DI)

- **Позитив:**
  - Все большие координаторы принимают зависимости через конструктор:
    - `DispatchService` получает сервисы `TargetPreparationService`, `DispatchExecutionService`, `FallbackService`, `ImageService | None`, `ILogger`.
    - `ImageService` принимает доменный `ImageGenerationService`, `PromptService`, UoW `IImageStorageUnitOfWork` и набор опциональных зависимостей (`ICache`, `IImageStorage`, `ICircuitBreaker`, `IMetrics`).
    - `PromptService`, `AdminDashboardService`, `APIStatusService`, `FrogRateLimiterService`, `FrogRequestService`, `TargetPreparationService`, `DispatchExecutionService`, `FallbackService` — все используют протоколы и доменные сервисы, а не конкретные infra‑реализации.
  - `BaseService` аккуратно инжектит логгер через `ILogger` и оборачивает его через `bind(service=...)`, давая полезный контекст.

- **Риски / замечания:**
  - `DatabaseOperationsService` допускает отсутствие `unit_of_work_factory` и тогда сам «дособирает» UoW — это скрытый DI‑антипаттерн.
  - В `AdminDashboardService` билдеры по умолчанию создаются внутри (`StatusMessageBuilder()`, `ModelsListMessageBuilder()`), что приемлемо (они чистые и не имеют внешних зависимостей), но их сложнее подменять в тестах.

### 2.3 Реализация паттернов (Unit of Work, Builder, BaseService)

- **Unit of Work:**
  - В `DatabaseOperationsService` UoW для БД реализован через протокол `IDatabaseUnitOfWork` и контекстный менеджер:

```78:99:src/app/database_operations_service.py
        async with uow:
            connection = uow.connection

            try:
                # 1. Отмечаем в реестре
                await self._dispatch_registry.mark_dispatched(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    chat_id=chat_id,
                    connection=connection,
                )

                # 2. Инкрементируем счётчик
                await self._usage_tracker.increment(1, connection=connection)

                # 3. Обновляем метрики (если доступны)
                if self._metrics:
                    await self._metrics.increment_dispatch_success(connection=connection)
```

  - **Плюсы:** логика «связанных операций БД в одной транзакции» действительно инкапсулирована в отдельном сервисе.
  - **Минус:** fallback‑импорты `infra.*` (см. выше) нарушают слой и «прячут» UoW‑конфигурацию от места сборки зависимостей.

- **Builder:**
  - `admin_dashboard_builders.py` реализует `StatusMessageBuilder` и `ModelsListMessageBuilder` поверх DTO `StatusData` и `ModelsListData`.
  - **Сильная сторона:** `AdminDashboardService` занимается только агрегацией данных, а форматирование вынесено в билдеры → это хороший пример разделения ответственности.

- **BaseService:**
  - Даёт единую точку входа для логгера и не добавляет ненужной логики.
  - **Ценность есть:** единый контракт `logger` и единое имя сервиса в контексте (`service=<ClassName>`), плюс инкапсуляция способа биндинга логгера.

### 2.4 Single Responsibility (SRP) координаторов

- **`DispatchService`** — чистый координатор cron‑рассылки:
  - не форматирует текст, не знает о Telegram‑типах;
  - управляет:
    - подготовкой целей (`TargetPreparationService`),
    - проверкой уже отправленных слотов,
    - генерацией изображения (`ImageService`),
    - fallback‑сценариями (`FallbackService`),
    - использованием коллбеков отправки.
  - **SRP соблюдён.**

- **`DispatchExecutionService`** — отвечает за отправку в конкретные чаты и запись результата:
  - отправка в один чат (`send_single_image`), учёт retry и метрик;
  - обход всех целей (`send_to_targets`), проверка `IDispatchRegistry`, вызов `DatabaseOperationsService`.
  - **SRP в целом соблюдён**, хотя часть логики регистрации успеха также повторяется во fallback‑сценариях.

- **`FallbackService`**:
  - покрывает:
    - отправку fallback‑изображений и дружелюбных сообщений,
    - работу с `DispatchResult`,
    - логирование и метрики ошибок.
  - **SRP соблюдён**, класс чётко отвечает за «что делать, когда основная генерация не удалась».

- **`ImageService`**:
  - координирует генерацию изображения с учётом circuit breaker, кэша, UoW и метрик;
  - бизнес‑правила (валидация промпта) находятся в доменном `ImageGenerationService`;
  - **SRP выдержан:** это именно application‑координатор, не смешивающийся с доменной валидацией.

- **`AdminDashboardService`**:
  - агрегирует usage, чаты, метрики и статусы API;
  - форматирование целиком делегировано билдерам;
  - **SRP выдержан.**

---

## 3. Логика, надёжность и устойчивость

### 3.1 Транзакции и Unit of Work

- **`DatabaseOperationsService.record_dispatch_success`**:
  - корректно использует `async with uow` и передаёт `connection` в `IDispatchRegistry` и `IUsageTracker`, а также в `IMetrics.increment_dispatch_success`.
  - при `RepoError` логирует ошибку и пробрасывает её дальше, полагаясь на UoW для отката транзакции.
  - **Транзакционность реализована правильно.**

- **`DatabaseOperationsService.record_dispatch_failure`**:
  - обновляет только метрики, **без транзакции**, что логично (метрики некритичны).

- **Использование UoW для хранения изображений:**
  - `ImageService` работает с `IImageStorageUnitOfWork.save_image` и при `StorageError` делает `rollback()`, обрабатывая возможные ошибки отката отдельно.
  - **Транзакционность хранения изображений реализована корректно на уровне application‑сервиса.**

### 3.2 Обработка ошибок и исключений

- **Широкие `except Exception` (риск):**
  - `DispatchService.send_wednesday_frog` ловит **любой** `Exception` и передаёт его в `FallbackService.handle_unexpected_error`, при этом логируя только не‑`ServiceError`:

```162:183:src/app/dispatch_service.py
        except Exception as e:
            import traceback
            ...
            if not isinstance(e, ServiceError):
                self.logger.error(
                    f"Неожиданная ошибка при выполнении рассылки: {e}",
                    ...
                    traceback=traceback.format_exc(),
                )
```

  - `DispatchExecutionService.send_single_image` имеет отдельный блок `except Exception`, который увеличивает `failed_count` и логирует ошибку.
  - `FallbackService.send_fallback_to_targets` также ловит общий `Exception` для каждой отправки.
  - `ImageService.generate_frog_image` в блоке генерации и сохранения изображений при неожиданных ошибках тоже использует `except Exception`.
  - `PromptService.generate`, `APIStatusService` методы проверки статуса и получения моделей также содержат `except Exception`.

- **Плюсы:**
  - Система везде стремится к graceful degradation — ошибки не роняют весь cron/бот, есть fallback‑пути.

- **Минусы:**
  - Широкие `except Exception` скрывают различие между ожидаемыми инфраструктурными/доменными ошибками и багами в коде.
  - Отсутствует единый подход/иерархия для «неожиданных программных ошибок» на уровне `app/` (всё сводится к логированию и fallback).

### 3.3 Circuit Breaker и fallback‑механизмы

- **Circuit breaker:**
  - `ImageService` использует `ICircuitBreaker`:
    - проверка `is_open()` в начале, с регистрацией метрики `record_circuit_breaker_trip`;
    - при `ImageGenerationError` вызывается `record_failure()`, с обработкой `CircuitBreakerOpen`.
  - **Плюсы:** circuit breaker чётко инкапсулирован в application‑слое и не смешан с доменной валидацией.

- **Fallback для изображений и промптов:**
  - `PromptService`:
    - сначала пытается получить промпт из кэша;
    - затем вызывает `PromptGenerationService.generate()` (доменный сервис);
    - при `None` использует `get_fallback_prompt()` (доменный fallback из конфигурации);
    - кэширует результат при успехе.
  - `FallbackService`:
    - при ошибке генерации (`handle_generation_failure`) и при неожиданных ошибках (`handle_unexpected_error`) переводит систему в fallback‑режим:
      - рассылает дружелюбное сообщение и fallback‑изображение (через коллбеки);
      - регистрирует успех через `DatabaseOperationsService`, считая такую отправку полноценной.

### 3.4 Асинхронность и производительность

- **Асинхронность:**
  - Все IO‑операции (`send_image`, кэш, UoW, репозитории, клиенты API) вызываются как `await`.
  - Сервисные методы в `app/` объявлены как `async def`.

- **Блокирующий I/O:**
  - В `image_service.py` используется только `time.perf_counter()` для замера латентности — это безопасный, очень быстрый вызов.
  - `time.sleep()` или синхронные HTTP‑клиенты не используются.
  - **Вывод:** критичных блокирующих операций в `app/` не обнаружено.

---

## 4. Качество кода и масштабируемость

### 4.1 Повторение логики и пересечение зон ответственности

- **`DispatchExecutionService` vs `FallbackService`:**
  - Оба сервиса:
    - проходят по множеству `targets`;
    - проверяют `IDispatchRegistry.is_dispatched` (в `FallbackService` для fallback‑отправки);
    - при успешной отправке вызывают `DatabaseOperationsService.record_dispatch_success`.
  - Различия:
    - `DispatchExecutionService` работает с основным изображением и `send_image`;
    - `FallbackService` с дружелюбным текстовым сообщением и `send_fallback_image`.
  - **Риск:** при изменении контракта `DatabaseOperationsService` или логики маркировки `DispatchResult` придётся править оба сервиса.
  - **Рекомендация:** рассмотреть вынос общей части в приватный helper или отдельный маленький сервис отправки «любого» payload с регистрацией, оставив `FallbackService` и `DispatchExecutionService` как thin‑координаторы над ним.

### 4.2 Типизация и DTO

- **Типизация:**
  - Используется современный синтаксис (`X | Y`, `set[int]`, `Callable[..., Awaitable[...]]`).
  - Все публичные методы координаторов типизированы, почти нет `Any`.

- **DTO / модели данных:**
  - `DispatchResult` — `TypedDict` с жёстко заданными полями; активно используется как mutable‑контейнер счётчиков.
  - `StatusData`, `ModelsListData` — `@dataclass` со строгой типизацией.
  - **Рекомендация (не критично):** рассмотреть замену `DispatchResult` на `@dataclass` с явными методами (`increment_success`, `increment_failure`, `mark_fallback_used`) для более безопасной работы, но текущий вариант допустим.

### 4.3 Масштабируемость архитектуры

- **Новые типы сообщений / сценариев:**
  - Структура координаторов (`TargetPreparationService`, `DispatchExecutionService`, `FallbackService`, `ImageService`, `PromptService`) выглядит устойчивой к появлению новых сценариев:
    - можно добавить новые application‑сервисы для других типов рассылок, переиспользуя базовые компоненты.

- **Новые AI‑провайдеры:**
  - Доменные сервисы уже завязаны на протоколы `ITextToImageClient`, `ITextToTextClient`.
  - `APIStatusService` инкапсулирует проверку статуса и список моделей, опираясь на `IModelsRepo`.
  - **Вывод:** добавление новых TTI/LLM‑провайдеров и переключение между ними потребует расширения `infra` и, возможно, небольших правок `APIStatusService` и билдеров, но не изменения общей структуры `app/`.

### 4.4 Чистота импортов

- Внутри `app/`:
  - нет циклических импортов между сервисами, кроме осмысленных зависимостей (например, `DispatchService` ← `DispatchExecutionService`/`FallbackService`/`ImageService`);
  - импорты из `infra` встречаются только в `DatabaseOperationsService` (проблемный fallback).
- В `shared.bot_services.BotServices`:
  - есть сильное сцепление с `infra.*` и `bot.wednesday_bot`, но **`app/` этот модуль не импортирует**, зависимости направлены **наружу** (бот/инфра зависят от app‑сервисов).

---

## 5. Критические проблемы

1. **Лик слоя и нарушение DI в `DatabaseOperationsService.record_dispatch_success`.**
   - Прямые импорты и создание `DatabaseUnitOfWork`, `get_postgres_pool`, `get_logger` внутри метода ломают границу `app/ → infra/`, затрудняют тестирование и противоречат текущему стилю использования протоколов.
   - **Рекомендация (высокий приоритет):**
     - Сделать `unit_of_work_factory` обязательной зависимостью (или передавать `IDatabaseUnitOfWork` напрямую при вызове).
     - Удалить fallback‑ветку с импортами `infra.*` из `app/` полностью.

2. **Широкие `except Exception` в координаторах без дифференциации «ожидаемых» и «неожиданных» ошибок.**
   - Скрывают реальные баги и приводят к тому, что любые ошибки выглядят как обычные сбои работы API/Telegram.
   - **Рекомендация (средний приоритет):**
     - Сузить перехватываемые исключения до ожидаемых (`ServiceError`, `RepoError`, специализированные ошибки клиентов).
     - Для по‑настоящему неожиданных ошибок либо пробрасывать их до верхнего уровня, либо оборачивать в отдельный тип (например, `UnexpectedDispatchError`) с явной пометкой в логах и метриках.

---

## 6. Технический долг и мелкие улучшения

- **`DispatchResult` как `TypedDict`:**
  - Удобен, но не даёт инкапсулировать инварианты (например, запрет отрицательных счётчиков).
  - **Улучшение:** со временем можно перейти на простой `@dataclass` с методами‑обёртками.

- **Повторение логики отправки и регистрации между `DispatchExecutionService` и `FallbackService`:**
  - В будущем при развитии логики регистрации (например, разные типы dispatch‑ов) понадобится рефакторинг в сторону общего сервиса.

- **APIStatusService — широкие `except Exception`:**
  - сейчас это удобно для защиты от любых неожиданностей внешних API, но полезно хотя бы разделить ожидаемые ошибки (`AuthenticationError`, `NetworkError`, `APIError`) и остальные.

- **Админ‑дашборд:**
  - `AdminDashboardService` дважды делает `TYPE_CHECKING: pass` — можно убрать лишний блок, это косметика.

---

## 7. Краткий обзор по файлам

- **`dispatch_service.py`**
  - Чистый координатор cron‑рассылки: использует `TargetPreparationService`, `DispatchExecutionService`, `FallbackService`, `ImageService`.
  - Зависит только от абстрактных коллбеков и сервисов, не знает о Telegram‑типаx; единственный минус — широкий `except Exception`.

- **`dispatch_execution_service.py`**
  - Отвечает за отправку в отдельные чаты, retry, учёт метрик и запись успешных отправок через `DatabaseOperationsService`.
  - Ошибки Telegram‑/сети обрабатываются специфично (`MessagingNetworkError`, `MessagingAPIError`), но есть общий `except Exception`.

- **`database_operations_service.py`**
  - Инкапсулирует транзакции с `IDatabaseUnitOfWork`; логика UoW реализована хорошо.
  - Критический дефект — fallback‑импорты `infra.*` при отсутствии фабрики UoW.

- **`image_service.py`**
  - Богатый, но хорошо структурированный координатор генерации изображений и кэширования.
  - Корректно использует circuit breaker, метрики, UoW для сохранения; широкие `except Exception` используются только для unexpected‑ошибок и сопровождаются детальным логированием.

- **`fallback_service.py`**
  - Формализует fallback‑сценарии, изолируя их от основной логики рассылки.
  - Содержит повтор логики обхода таргетов и регистрации успеха; есть общий `except Exception` в отправке по каждому чату.

- **`prompt_service.py`**
  - Координатор генерации промптов с кэшированием и fallback‑логикой.
  - Ловит общий `Exception` в генерации и fallback‑получении; для доменного слоя это было учтено в `DOMAIN_LAYER_AUDIT`, здесь стоит только сузить типы на уровне app‑сервиса там, где речь о кэше.

- **`target_preparation_service.py`**
  - Чистый сервис для подготовки списка чатов и проверки «already dispatched for all».
  - Не зависит от `bot/`, работает через `IChatsRepo` и `IDispatchRegistry`.

- **`admin_dashboard_service.py` + `admin_dashboard_builders.py`**
  - Хорошее разделение «агрегация данных» vs «форматирование».
  - Зависимости через протоколы и `APIStatusService`; слой `app/` не знает о Telegram.

- **`api_status_service.py`**
  - Координатор поверх клиентов `ITextToImageClient`, `ITextToTextClient` и `IModelsRepo`.
  - Много широких `except Exception`, но они сопровождаются подробным логированием и укладываются в стратегию «не ронять дашборд из‑за статуса API».

- **`frog_limit_service.py` (`FrogRateLimiterService`)**
  - Инкапсулирует rate‑limiting команды `/frog` поверх `IRateLimiter` и `AppSettings`.
  - Не зависит от `bot/` и Telegram, возвращает `(is_allowed, user_message)` как чистый результат.

- **`frog_requests.py` (`FrogRequestService`)**
  - Тонкий фасад над `ITaskQueue`, скрывает детали постановки задач от хендлеров.

- **`dispatch_result.py`**
  - `TypedDict`‑DTO для результата рассылки; активно используется во всех координаторах.

- **`__init__.py`**
  - Только строка документации — корректно.

---

## 8. План рефакторинга (по шагам)

### Шаг 1. Устранить жёсткую зависимость `DatabaseOperationsService` от `infra`

- **Цель:** полностью убрать импорты `infra.*` из `src/app/database_operations_service.py`.
- **Действия:**
  1. Сделать аргумент `unit_of_work_factory: Callable[[], IDatabaseUnitOfWork]` **обязательным** в конструкторе `DatabaseOperationsService` (без значения по умолчанию).
  2. Удалить ветку:
     - `if self._unit_of_work_factory is None: ... from infra...`
  3. Перенести сборку `DatabaseUnitOfWork`, `get_postgres_pool`, `get_logger` в слой `infra` / точку компоновки зависимостей ( в контейнер, где создаётся `DatabaseOperationsService`).
  4. Обновить места создания `DatabaseOperationsService` (в `infra` или `bot`), передавая корректную фабрику UoW.

### Шаг 2. Сузить обработку исключений и ввести иерархию «неожиданных» ошибок

- **Цель:** отличать ожидаемые инфраструктурные/доменные ошибки от программных багов.
- **Действия:**
  1. В `DispatchService`, `DispatchExecutionService`, `FallbackService`, `ImageService`, `PromptService`, `APIStatusService`:
     - заменить `except Exception` на перехват конкретных типов (например, `ServiceError`, `RepoError`, `MessagingAPIError`, `MessagingNetworkError`, `StorageError`, `CacheError`);
     - для truly unexpected ошибок:
       - оборачивать его в специальный тип (`UnexpectedDispatchError`, `UnexpectedImageError`) и бросать дальше, чтобы верхний уровень мог отреагировать.
  2. Зафиксировать в документации (например, в `docs/ARCHITECTURE.md`) общую стратегию обработки ошибок в `app/`‑слое.

### Шаг 3. Упростить и унифицировать обработку dispatch‑ов и fallback‑отправок

- **Цель:** сократить дублирование между `DispatchExecutionService` и `FallbackService`.
- **Действия:**
  1. Выделить или небольшой сервис (например, `DispatchRecordService`), который:
     - принимает `DispatchResult`, `slot_date`, `slot_time`, `targets`, функцию отправки (`send_callable`) и коллбеки для сообщений/ошибок;
     - внутри использует `IDispatchRegistry` и `DatabaseOperationsService` для регистрации успеха/неуспеха.
  2. Перевести `DispatchExecutionService.send_to_targets` и `FallbackService.send_fallback_to_targets` на использование этого helper‑а, сохранив различия только в передаваемых коллбеках (`send_image` vs `send_fallback_image` + `send_user_friendly_error`).

### Шаг 4. Небольшие улучшения качества кода

- **Цель:** вычистить технический долг без серьёзных архитектурных изменений.
- **Действия:**
  1. В `admin_dashboard_service.py` удалить дублирующий блок `if TYPE_CHECKING: pass`.
  2. Рассмотреть перевод `DispatchResult` в `@dataclass` с явными методами‑мутаторами, если в будущем появятся дополнительные поля или инварианты.
  3. По возможности выровнять сообщения логов и событий (`event=...`) между сервисами, чтобы упростить анализ логов и метрик.

---

## 9. Заключение

- Слой `app/` в целом **соответствует роли application‑координатора**: он не знает о деталях Telegram, баз данных и конкретных клиентов, опирается на протоколы и доменные сервисы, инкапсулирует сценарии и транзакции.
- Главный архитектурный дефект — **fallback‑зависимость от `infra` в `DatabaseOperationsService`** — локализован и относительно легко устраним.
- После его устранения и небольшого упорядочивания обработки ошибок слой `app/` будет хорошо готов к дальнейшему росту (новые команды, новые провайдеры, дополнительные метрики и сценарии), сохраняя чистые границы между `domain/`, `app/`, `infra/` и `bot/`.

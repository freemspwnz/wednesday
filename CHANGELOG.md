# CHANGELOG

## [Unreleased]

### Изменено

- **Рефакторинг GigaChatTextClient для устранения сильной связности с Postgres**:
  - Параметр `models_repo` теперь обязательный (убрана опциональность `| None`)
  - Убраны внутренние вызовы `get_postgres_pool()` и создание `ModelsRepo` внутри клиента
  - Удалён неиспользуемый импорт `ModelsRepo` из `gigachat_text.py`
  - Обновлён `ClientManagementService` для обязательной передачи `models_repo` в конструктор
  - Добавлена валидация наличия `models_repo` при создании клиентов через `ClientManagementService`

### Добавлено

- **ClientManagementService для управления клиентами ML-сервисов**:
  - Создан новый сервис `src/infra/clients/client_manager.py` для централизованного создания клиентов
  - Реализованы методы `create_image_client()` и `create_text_client()` для создания клиентов с кастомными конфигами
  - Поддержка runtime-замены клиентов без рестарта приложения
  - Интеграция с репозиторием моделей через dependency injection

- **Улучшение контракта PromptGenerationService.generate**:
  - Добавлен enum `PromptSource` с тремя значениями: `AI`, `FALLBACK_REQUIRED`, `UNAVAILABLE`
  - Добавлен dataclass `PromptGenerationResult` с полями `prompt` и `source` для явного указания источника промпта
  - Метод `generate()` теперь возвращает `PromptGenerationResult` вместо `str | None`
  - Неожиданные ошибки теперь пробрасываются дальше для обработки в app-слое

### Изменено

- **Упрощение обработки рассылок и fallback-отправок в app-слое**:
  - Добавлен общий helper `process_targets_with_registry_check()` в модуль `app/dispatch_targets_helper.py`
  - `DispatchExecutionService.send_to_targets()` переведён на использование общего helper-а вместо собственного цикла по таргетам
  - `FallbackService.send_fallback_to_targets()` переведён на использование общего helper-а с сохранением текущей семантики обработки ошибок
  - Убрано дублирование логики проверки `IDispatchRegistry.is_dispatched()` и логирования пропусков в сервисах рассылок
  - Упростилась дальнейшая эволюция логики обхода таргетов и регистрации отправок

- **Обновлены контейнеры клиентов для работы с ClientManagementService**:
  - Метод `replace_client()` в `ImageClientContainer` теперь принимает `config` и `client_manager` вместо готового клиента
  - Метод `replace_client()` в `TextClientContainer` теперь принимает `config` и `client_manager` вместо готового клиента
  - Обновлены docstring модулей контейнеров для отражения нового подхода к созданию клиентов
  - Клиенты теперь создаются через `ClientManagementService` с кастомными конфигами для runtime-замены

- **Рефакторинг container.py для использования ClientManagementService**:
  - Удален импорт `create_image_client` и `create_text_client` из `infra.clients.factory`
  - Добавлен импорт `ClientManagementService` и функций получения контейнеров
  - Полностью переписана функция `_create_clients()` для использования `ClientManagementService` и регистрации клиентов в контейнерах
  - Обновлены комментарии в `build_image_stack()` для отражения нового подхода через DI
  - Клиенты теперь регистрируются в контейнерах для поддержки runtime-замены и корректного cleanup

- **Удаление устаревшего factory.py и обновление экспортов**:
  - Удален файл `src/infra/clients/factory.py` (заменен на `ClientManagementService`)
  - Обновлен `src/infra/clients/__init__.py`: удалены экспорты `create_image_client` и `create_text_client`
  - Добавлен экспорт `ClientManagementService` в `__init__.py`
  - Обновлен docstring модуля для отражения нового подхода через DI и контейнеры
  - Обновлены тесты в `tests/test_smoke_low_coverage.py` для использования `ClientManagementService` вместо factory

- **Обновление документации после рефакторинга клиентов**:
  - Обновлен `docs/ARCHITECTURE.md`: заменены упоминания factory на `ClientManagementService` и обновлены описания DI
  - Обновлен `docs/TESTING_GUIDE.md`: примеры использования обновлены для нового подхода через `_create_clients()`
  - Все тесты обновлены для использования нового API `replace_client()` с `config` и `client_manager`

- **Рефакторинг конфигурации: завершен переход на Pydantic Config**:
  - Полностью завершен переход с dataclass на Pydantic BaseSettings для всех моделей конфигурации
  - Все модули используют единый `Config` класс из `shared.config`
  - Удалены все упоминания старого Config (dataclass версия) и ConfigV2
  - Все тесты обновлены для работы с Pydantic моделями
  - Конфигурация теперь полностью основана на Pydantic с валидацией и поддержкой переменных окружения

- **Рефакторинг конфигурации: обновление тестов**:
  - Обновлен `tests/conftest.py`: удален дублирующий импорт, убраны проверки на старый Config
  - Переименован файл `tests/shared/test_config_v2.py` → `tests/shared/test_config.py`
  - Обновлены имена тестов: `test_config_v2_*` → `test_config_*`
  - Обновлен тест `test_config_direct_access`: используется прямой доступ к конфигурации вместо методов преобразования
  - Удален старый `tests/shared/test_config.py` (тесты для старой dataclass версии)
  - Проверены все тестовые файлы: `tests/infra/clients/test_gigachat_text_client.py` и `tests/test_smoke_low_coverage.py` используют Pydantic-версии конфигураций

- **Рефакторинг конфигурации: переименование и обновление импортов**:
  - Переименован класс `ConfigV2` → `Config` в новом `config.py`
  - Переименован файл `config_v2.py` → `config.py`
  - Обновлены все импорты: `from shared.config_v2 import ConfigV2` → `from shared.config import Config`
  - Обновлены все импорты классов конфигурации: `from shared.config_v2 import ...` → `from shared.config import ...`
  - Обновлены глобальные экземпляры: `config: ConfigV2 = ConfigV2()` → `config: Config = Config()`
  - Обновлены все типизации: `ConfigV2` → `Config`
  - Удален старый файл `config.py` (dataclass версия)
  - Удален файл `config_v2.py` после переноса содержимого в `config.py`
  - Обновлены тесты для использования нового `Config` класса

- **Рефакторинг конфигурации: обновление остальных модулей**:
  - Обновлен `src/shared/bot_services.py`: заменен импорт `AppSettings` на Pydantic-версию из `config_v2`
  - Обновлен `src/app/frog_limit_service.py`: заменен импорт `AppSettings` на Pydantic-версию из `config_v2`
  - Обновлен `src/bot/support_bot.py`: заменен вызов `config.to_app_settings()` на прямое создание `AppSettings()` из `config_v2`
  - Обновлен `src/shared/retry.py`: заменены все вызовы `config.to_retry_config()` на прямое использование `config.retry`
  - Обновлены все модули с типизацией `Config | ConfigV2`: заменены на `ConfigV2`, удалены импорты старого `Config`
  - Обновлены сигнатуры функций в `celery/context.py`, `postgres_client.py`, `admins_repo.py`, `redis_client.py` для использования только `ConfigV2`

- **Рефакторинг конфигурации: удаление методов преобразования из ConfigV2**:
  - Обновлен `_create_clients()` в `container.py`: удалены проверки `isinstance(config, ConfigV2)`, теперь всегда используется `ConfigV2`
  - Обновлен `build_image_stack()` в `container.py`: заменен вызов `config.to_circuit_breaker_config()` на прямое использование `config.circuit_breaker`
  - Обновлен `build_bot_services()` в `container.py`: заменен вызов `config.to_app_settings()` на прямое создание `AppSettings()` из `config_v2`
  - Удалены все методы преобразования из `ConfigV2`: `to_gigachat_config()`, `to_kandinsky_config()`, `to_app_settings()`, `to_retry_config()`, `to_circuit_breaker_config()`
  - Обновлены сигнатуры функций в `container.py`: все функции теперь принимают только `ConfigV2`, а не `Config | ConfigV2`

- **Рефакторинг конфигурации: обновление клиентов для работы с Pydantic-моделями**:
  - Обновлен `src/infra/clients/kandinsky.py`: заменен импорт `KandinskyConfig` на версию из `config_v2`
  - Обновлен `src/infra/clients/gigachat_text.py`: заменен импорт `GigaChatConfig` на версию из `config_v2`
  - Обновлен `src/infra/clients/factory.py`: импорты `GigaChatConfig` и `KandinskyConfig` заменены на версии из `config_v2`

- **Рефакторинг конфигурации: преобразование dataclass'ов в Pydantic модели**:
  - Переименованы классы в `config_v2.py`: `KandinskyConfigV2` → `KandinskyConfig`, `GigaChatConfigV2` → `GigaChatConfig`, `RetryConfigV2` → `RetryConfig`, `CircuitBreakerConfigV2` → `CircuitBreakerConfig`, `AppSettingsConfig` → `AppSettings`
  - Преобразован `ImageConfig` в Pydantic BaseModel с ClassVar полями для констант
  - Преобразован `PromptFallbackConfig` в Pydantic BaseModel с полями `frog_prompts` и `styles`
  - Обновлены ссылки на переименованные классы в `ConfigV2` (поля `kandinsky`, `gigachat`, `retry`, `circuit_breaker`)

- **Обновление PromptService для работы с новым контрактом PromptGenerationService**:
  - Метод `generate()` обновлен для работы с `PromptGenerationResult` вместо `str | None`
  - Убрана обработка ожидаемых исключений клиентов (AuthenticationError, NetworkError, APIError, ClientError), так как они теперь обрабатываются в domain-слое
  - Добавлена обработка разных источников промпта через `PromptSource` enum
  - Улучшено логирование различных сценариев генерации промпта

- **Вынесение дефолтного fallback-промпта из кода PromptGenerationService**:
  - Добавлено поле `default_fallback_prompt` в класс `PromptFallbackConfig` в `config.py` с дефолтным значением
  - Убрана захардкоженная строка из метода `get_fallback_prompt()` в `PromptGenerationService`
  - Метод `get_fallback_prompt()` теперь использует `self._fallback_config.default_fallback_prompt` из конфига
  - Дефолтный промпт теперь является частью конфигурации, что позволяет настраивать его через dependency injection без изменений доменного кода

- **Уточнение обработки неожиданных ошибок в ImageGenerationService**:
  - Добавлен класс `UnexpectedImageGenerationError`, наследующий от `ImageGenerationError`
  - Метод `generate()` в `ImageGenerationService` теперь использует `UnexpectedImageGenerationError` для неожиданных ошибок
  - Позволяет app-слою отличать ожидаемые бизнес-ошибки от инцидентов, требующих отдельного логирования/алертинга

### Добавлено

- **Поддержка pydantic-settings для новой структуры конфигурации**:
  - Добавлена зависимость `pydantic-settings>=2.0.0` в `requirements.txt` и `pyproject.toml`
  - Подготовка к миграции на Pydantic BaseSettings для управления конфигурацией

- **Новая структура конфигурации на основе Pydantic (config_v2.py)**:
  - Создан модуль `src/shared/config_v2.py` с вложенными Pydantic моделями
  - Реализованы модели: `TelegramConfig`, `KandinskyConfig`, `GigaChatConfig`, `PostgresConfig`, `RedisConfig`, `SchedulerConfig`, `SentryConfig`, `RetryConfig`, `CircuitBreakerConfig`, `AppSettingsConfig`
  - Добавлена поддержка чтения секретов из файлов через переменные *_FILE через валидаторы
  - Главная модель `ConfigV2` объединяет все вложенные конфигурации
  - Сохранены константы `ImageConfig` и `PromptFallbackConfig` для обратной совместимости
  - Добавлены методы преобразования новых моделей в старые dataclass'ы для обратной совместимости

- **Миграция infra/ модулей на поддержку ConfigV2**:
  - Обновлен `postgres_client.py`: функции `init_postgres_pool()` и `ensure_database()` принимают параметр `config`
  - Обновлен `redis_client.py`: функция `get_redis_url()` принимает параметр `config`
  - Обновлен `celery/context.py`: функции `_ensure_pools_initialized()` и `get_services_context()` принимают параметр `config_obj`
  - Обновлен `celery/app.py`: поддержка ConfigV2 для всех настроек scheduler и Celery
  - Обновлен `repos/admins_repo.py`: конструктор принимает параметры `admin_chat_id` и `config_obj`
  - Обновлен `logging/logger.py`: поддержка ConfigV2 для получения секретов и log_level
  - Все модули сохраняют обратную совместимость с глобальным config

- **Добавлены тесты для ConfigV2**:
  - Создан `tests/shared/test_config.py` с комплексными тестами новой структуры конфигурации
  - Тесты проверяют создание ConfigV2 из переменных окружения
  - Тесты проверяют model_validate для создания конфигураций в тестах
  - Тесты проверяют поддержку чтения секретов из файлов через *_FILE переменные
  - Тесты проверяют методы преобразования в старые dataclass'ы
  - Тесты проверяют валидацию всех вложенных моделей (HttpTimeoutConfig, SchedulerConfig, PostgresConfig, RedisConfig)
  - Обновлен `tests/conftest.py` для поддержки ConfigV2 при создании postgres pool

- **Обновление main.py и остальных модулей для использования ConfigV2**:
  - Обновлен `main.py`: использует ConfigV2 вместо старого Config
  - Обновлен `bot/support_bot.py`: использует ConfigV2 с fallback на старый Config
  - Обновлен `bot/wednesday_bot.py`: использует ConfigV2 с fallback на старый Config
  - Обновлен `shared/retry.py`: использует ConfigV2 для получения retry конфигурации
  - Обновлен `celery/app.py`: использует ConfigV2 вместо старого Config
  - Обновлен `celery/context.py`: использует ConfigV2 с fallback
  - Старый Config класс помечен как DEPRECATED, методы from_config() также помечены как устаревшие
  - Глобальный экземпляр старого config удалён в пользу ConfigV2

### Технические детали миграции

Миграция на новую структуру конфигурации выполнена с сохранением полной обратной совместимости:
- Старый `Config` класс продолжает работать
- Все модули поддерживают как `Config`, так и `ConfigV2`
- Методы преобразования позволяют использовать новые модели с кодом, ожидающим старые dataclass'ы
- Постепенный переход: можно использовать ConfigV2 в новых местах, старый код продолжает работать

### Изменено

- **Обновлен container.py для поддержки новой конфигурации**:
  - Добавлена поддержка `ConfigV2` в функциях `_create_clients()`, `build_image_stack()`, `build_bot_services()`, `build_bot()`
  - Функции теперь принимают как `Config`, так и `ConfigV2` для постепенной миграции
  - Использование методов преобразования для создания старых dataclass'ов из новых Pydantic моделей

- **Перенос retry логики с domain слоя на уровень клиента**:
  - Удален импорт `retry_standard` из `domain/image_generation.py`
  - Убран декоратор `@retry_standard` с метода `generate()` в `ImageGenerationService`
  - Обновлен docstring метода `generate()` - указано, что retry логика применяется на уровне клиента (ITextToImageClient)
  - Обновлены комментарии в `app/image_service.py` - указано, что retry логика находится на уровне клиента, а не в domain слое

- **Удаление логирования из domain слоя**:
  - Удалено наследование от `BaseService` в трех domain сервисах: `PromptGenerationService`, `ImageGenerationService`, `CaptionService`
  - Убраны все вызовы `self.logger` из domain сервисов для обеспечения чистоты доменного слоя
  - Удален параметр `logger` из `__init__` методов всех domain сервисов
  - Обновлен `container.py` - убрана передача `logger=app_logger` при создании domain сервисов
  - Обновлены тесты - убрана передача `logger=_create_mock_logger()` из вызовов конструкторов domain сервисов
  - Добавлено логирование в app слой (`PromptService`, `ImageService`) вокруг вызовов domain сервисов для сохранения наблюдаемости

- **Инъекция зависимостей для логирования в BaseService**:
  - `BaseService` теперь принимает `logger: ILogger` через конструктор (обязательный параметр)
  - Все сервисы, наследующиеся от `BaseService`, обновлены для принятия `logger` в конструкторе
  - `BaseService.__init__` использует `logger.bind(service=self.__class__.__name__)` для автоматической привязки контекста сервиса
  - Удалены все прямые импорты `get_logger` из сервисов - создание логгеров перенесено в Composition Root
  - В `container.py` и `support_bot.py` создается один общий `app_logger = get_logger("app")`, который передается всем сервисам
  - Все вызовы `self.log_event()` заменены на `self.logger.info/warning/error/debug()` с передачей структурированных данных (`event`, `status`, `user_id`, `extra`) через `**kwargs`
  - Метод `LoguruLogger._log()` автоматически извлекает структурированные параметры из `kwargs` и передает их в функцию `log_event()`, сохраняя структурированность логирования
  - `RedisBackendService` (базовый класс для Redis-сервисов) принимает опциональный `logger` с fallback на `get_logger()` для обратной совместимости
  - Модули больше не зависят от библиотеки loguru напрямую, работают только с интерфейсом `ILogger`
  - В тестах добавлены mock-логгеры (через helper-функции `_create_mock_logger()`) для всех сервисов, создаваемых в тестах

- **Рефакторинг DatabaseOperationsService для явной инъекции UnitOfWork**:
  - Аргумент `unit_of_work_factory: Callable[[], IDatabaseUnitOfWork]` сделан обязательным в конструкторе `DatabaseOperationsService`
  - Удалён fallback-код, создающий `DatabaseUnitOfWork` и логгер внутри `DatabaseOperationsService` через импорты из `infra.*`
  - Сборка `DatabaseUnitOfWork` и логгера перенесена в composition root (`container.py`), где теперь передаётся фабрика UoW
  - Интеграционные тесты `tests/app/test_database_operations_service.py` обновлены для передачи собственной фабрики UnitOfWork

- **Рефакторинг логирования для обеспечения чистой инъекции зависимостей**:
  - Создан протокол `ILogger` в `shared/protocols.py` с методами trace, debug, info, success, warning, error, critical (с поддержкой *args и **kwargs) и методом bind(**kwargs) -> ILogger
  - Создан класс `LoguruLogger` в `infra/logging/logger.py`, реализующий протокол `ILogger`
  - Все методы логгера (`info`, `error` и т.д.) внутри `LoguruLogger` вызывают существующую функцию `log_event` для гарантии очистки данных перед записью
  - Реализован метод `bind` в `LoguruLogger`, который возвращает новый экземпляр с обновленным контекстом
  - Обновлена функция `get_logger(name)` для возврата экземпляра `LoguruLogger` вместо прямого объекта loguru
  - Добавлена поддержка параметра `exc_info` в функцию `log_event` для корректной обработки исключений
  - Добавлена поддержка форматирования строк через позиционные аргументы (*args) в методах логирования
  - Заменены все использования `logger.exception()` на `logger.error(..., exc_info=True)` для соответствия протоколу
  - Сохранен класс `LoguruHandler` для перехвата логов от uvicorn и других библиотек, использующих стандартный logging
  - Декоратор `log_execution` и функция `log_event` продолжают работать корректно с новой структурой

- **Объединение модулей обработки ошибок клиентов**:
  - Объединены `error_handling.py` и `sber_clients_exceptions.py` в один модуль
  - Функция `should_retry` перенесена в `sber_clients_exceptions.py`
  - Удалён неиспользуемый модуль `error_handling.py`
  - Удалена неиспользуемая функция `log_client_error` (логирование уже есть в декораторе `map_client_errors`)
  - Упрощена структура модулей клиентов

- **Добавление декоратора для обработки ошибок клиентов**:
  - Создан декоратор `map_client_errors` в `sber_clients_exceptions.py`
  - Декоратор автоматически обрабатывает доменные исключения, ValidationError и неожиданные исключения
  - Внедрен декоратор во все публичные методы `KandinskyClient` и `GigaChatTextClient`
  - Удалены повторяющиеся блоки обработки ошибок из клиентов (~100+ строк кода)
  - Упрощена обработка ValidationError - теперь централизована в декораторе
  - Улучшена читаемость кода клиентов за счет удаления boilerplate кода

- **Устранение протечки абстракций: перенос исключений клиентов в доменный слой**:
  - Перенесены HTTP ошибки из `infra/clients/exceptions.py` в `shared/base/exceptions.py`
  - Доменные исключения (`ClientError`, `AuthenticationError`, `RateLimitError`, `NetworkError`, `APIError`) теперь без `status_code` и `response_body`, только `message` и `original_error`
  - Переименован `infra/clients/exceptions.py` в `sber_clients_exceptions.py`
  - Функция `map_http_status_to_exception` переименована в `map_http_status_to_domain_exception` (с алиасом для обратной совместимости)
  - Обновлены протоколы `ITextToTextClient` и `ITextToImageClient` - теперь указывают доменные исключения в docstrings
  - Заменены импорты в domain слое (`image_generation.py`, `prompt_generation.py`) на доменные исключения
  - Обновлены все использования клиентских исключений в infra/clients
  - Удалено использование `status_code` и `response_body` из всех мест создания исключений
  - Domain слой больше не зависит от infra слоя

- **Добавление протокола IImageStorageUnitOfWork**:
  - Создан протокол `IImageStorageUnitOfWork` в `shared/protocols.py`
  - Заменено прямое использование `ImageStorageUnitOfWork` на протокол `IImageStorageUnitOfWork` в `ImageService`
  - Улучшена тестируемость и возможность замены реализации
  - Протокол определяет методы: `save_image()` и `rollback()`

- **Замена time.time() на time.perf_counter() для измерения производительности**:
  - Заменены все использования `time.time()` на `time.perf_counter()` в `image_service.py`
  - Улучшена точность измерения производительности генерации изображений
  - `time.perf_counter()` более точен для измерения времени выполнения, так как не подвержен системным корректировкам часов

- **Устранение создания зависимостей внутри конструкторов**:
  - Убрано создание `DatabaseOperationsService` внутри конструктора `DispatchExecutionService`
  - Убрано создание `ImageStorageUnitOfWork` внутри конструктора `ImageService`
  - Все зависимости теперь передаются через конструктор (принцип Dependency Injection)
  - `database_operations` теперь обязательный параметр в `DispatchExecutionService.__init__`
  - `storage_unit_of_work` теперь обязательный параметр в `ImageService.__init__` (перемещен перед опциональными параметрами)
  - Обновлен порядок параметров в `ImageService.__init__` для соответствия правилам Python
  - Все зависимости создаются в DI-контейнере (`container.py`)

- **Устранение дублирования логики регистрации отправок**:
  - Удален дублирующийся код регистрации отправок из `FallbackService`
  - `database_operations` теперь обязательный параметр в `FallbackService.__init__`
  - Все сервисы используют единый метод `DatabaseOperationsService.record_dispatch_success()` для регистрации
  - Упрощена логика в `FallbackService.send_fallback_to_targets()` - удалена fallback логика с прямыми вызовами
  - Обновлен порядок параметров в `FallbackService.__init__` для соответствия правилам Python

- **Рефакторинг обработки исключений в app/ слое**:
  - Добавлены доменные исключения `RepoError` и `ServiceError` в `shared/base/exceptions.py`
  - Заменено избыточное использование `except Exception` на специфичные исключения во всех сервисах app/
  - Добавлено структурированное логирование через `log_event` для всех типов ошибок
  - Ошибки кэша обрабатываются через `CacheError` с логированием
  - Ошибки хранилища обрабатываются через `StorageError` с логированием
  - Ошибки репозиториев обрабатываются через `RepoError` с логированием
  - Ошибки сервисов обрабатываются через `ServiceError` с логированием
  - Неожиданные ошибки логируются с полным traceback через структурированное логирование
  - Обновлены файлы: `dispatch_execution_service.py`, `fallback_service.py`, `image_service.py`, `api_status_service.py`, `database_operations_service.py`, `dispatch_service.py`, `prompt_service.py`, `admin_dashboard_service.py`

- **Замена dict на TypedDict для DispatchResult**:
  - Заменен класс `DispatchResult(dict)` на `TypedDict` в `app/dispatch_result.py`
  - Добавлена явная типизация всех полей: `slot_date`, `slot_time`, `total_targets`, `success_count`, `failed_count`, `used_fallback`
  - Улучшена типобезопасность и валидация полей на этапе разработки
  - Обновлена документация и тесты для работы с новым типом `DispatchResult`

- **Уточнение стратегии обработки ошибок в слое app/**:
  - Добавлена иерархия `UnexpectedAppError` и специализированные исключения `UnexpectedDispatchError`, `UnexpectedImageError`, `UnexpectedPromptError`, `UnexpectedAPIError` в `shared.base.exceptions`
  - В `DispatchService`, `DispatchExecutionService`, `FallbackService`, `ImageService`, `PromptService`, `APIStatusService` сузены широкие `except Exception` до обработки конкретных доменных/инфраструктурных ошибок
  - Для действительно неожиданных ошибок (`Exception`, не являющихся доменными/инфраструктурными) реализовано оборачивание в `Unexpected*Error` и проброс выше по стеку с подробным структурированным логированием
  - В `docs/ARCHITECTURE.md` зафиксирована общая стратегия обработки ожидаемых и неожиданных ошибок в слое `app/`
  - Все существующие использования остаются совместимыми

- **Рефакторинг зависимостей от infra/ в app/ слое**:
  - Созданы протоколы `IDispatchRegistry` и `IDatabaseUnitOfWork` в `shared/protocols.py`
  - Заменены прямые зависимости от `DispatchRegistry` на `IDispatchRegistry` в сервисах app/
  - Заменено использование `DatabaseUnitOfWork` на `IDatabaseUnitOfWork` через фабрику
  - Обновлены сервисы: `DispatchExecutionService`, `FallbackService`, `TargetPreparationService`, `DatabaseOperationsService`
  - Обновлен `container.py` для передачи фабрики Unit of Work
  - Устранено нарушение границ слоёв и улучшена тестируемость

### Добавлено

- **Доменные исключения для мессенджеров**:
  - Создан модуль `shared/base/exceptions.py` с доменными исключениями
  - Определены классы: `AppError` (базовый), `MessagingError`, `MessagingNetworkError`, `MessagingAPIError`
  - Все ошибки мессенджера имеют общий корень `MessagingError`

- **Протокол IMessagingService**:
  - Добавлен протокол `IMessagingService` в `shared/protocols.py`
  - Определены методы: `send_image()` и `send_message()`
  - Абстрагирует детали реализации мессенджера от application-сервисов

- **Реализация PTBMessagingService**:
  - Создан модуль `infra/messaging/ptb.py` с реализацией `IMessagingService` через python-telegram-bot
  - Создан декоратор `map_telegram_exceptions` в `infra/messaging/ptb_exceptions.py` для маппинга `telegram.error` → доменные исключения
  - Декоратор автоматически преобразует `NetworkError`/`TimedOut` → `MessagingNetworkError`, `TelegramError` → `MessagingAPIError`

### Изменено

- **Рефакторинг зависимостей от telegram.error**:
  - Обновлен `app/dispatch_execution_service.py` для использования доменных исключений вместо `telegram.error`
  - Обновлен `shared/retry.py` для работы с доменными исключениями мессенджеров
  - Удалены прямые зависимости от `telegram.error` в app-слое

- **Переименование методов отправки изображений**:
  - Переименован метод `send_single_photo()` → `send_single_image()` в `DispatchExecutionService`
  - Переименован параметр `send_photo` → `send_image` в методах сервисов
  - Переименован параметр `photo` → `image` в протоколе `IMessagingService`
  - Обновлены все вызовы и комментарии для использования единообразной терминологии

### Добавлено

- **Классификация операций по критичности**:
  - Создан документ `docs/OPERATIONS_CRITICALITY.md` с классификацией операций
  - Определены критичные операции: регистрация отправок, обновление счётчиков, сохранение изображений, операции с пользовательскими данными
  - Определены некритичные операции: кэширование, метрики, логирование событий, проверка статуса API
  - Описаны стратегии обработки ошибок для каждой категории операций
  - Документ служит основой для систематизации обработки ошибок в системе

- **DatabaseUnitOfWork для управления транзакциями БД**:
  - Создан класс `DatabaseUnitOfWork` в `services/infrastructure/database_unit_of_work.py`
  - Реализован паттерн Unit of Work для группировки операций БД в одну транзакцию
  - Поддержка async context manager для автоматического коммита/отката
  - Методы: `begin()`, `commit()`, `rollback()`, `connection` property
  - Надёжная обработка ошибок с гарантированным освобождением соединений
  - Защита от повторного коммита/отката транзакций

- **Поддержка опционального соединения в репозиториях**:
  - Добавлен параметр `connection` в `DispatchRegistry.mark_dispatched()` для использования в транзакциях
  - Добавлен параметр `connection` в `UsageTracker.increment()` для использования в транзакциях
  - Добавлен параметр `connection` во все методы increment класса `Metrics` для использования в транзакциях
  - Репозитории теперь могут работать как с переданным соединением (в транзакции), так и с новым соединением из пула

- **DatabaseOperationsService для групповых операций БД**:
  - Создан сервис `DatabaseOperationsService` в `services/application/database_operations_service.py`
  - Реализован метод `record_dispatch_success()` для атомарной регистрации успешной отправки
  - Реализован метод `record_dispatch_failure()` для регистрации неуспешной отправки
  - Использует `DatabaseUnitOfWork` для обеспечения атомарности операций
  - Группирует операции: регистрация отправки, инкремент счётчика, обновление метрик в одной транзакции

### Изменено

- **Массовый рефакторинг архитектуры проекта (структура файлов и директорий)**:
  - Перемещен `services/bot_services.py` → `shared/bot_services.py` (DI-контейнер в общий слой)
  - Перемещен `utils/config.py` → `shared/config.py` (конфигурация в общий слой)
  - Перемещен `utils/redis_client.py` → `infra/redis/redis_client.py` (инфраструктурный компонент)
  - Перемещен `utils/retry.py` → `shared/retry.py` (общий механизм retry)
  - Перемещен `utils/paths.py` → `shared/paths.py` (общие константы путей)
  - Добавлена константа `PROMPTS_DIR` в `shared/paths.py` для консистентности
  - Обновлены все импорты во всех модулях проекта (более 50 файлов)
  - Обновлены импорты в тестах
  - Обновлен `pyproject.toml`: удалены `"services"` и `"utils"` из `known-first-party`
  - Удалены пустые директории `services/` и `utils/`
  - Рефакторинг улучшает структуру проекта в соответствии с принципами Clean Architecture:
    * Общие компоненты (config, retry, paths, bot_services) находятся в `shared/`
    * Инфраструктурные компоненты (redis_client) находятся в `infra/`
    * Четкое разделение ответственности между слоями

- **Перемещена директория application в корень проекта**:
  - Директория `services/application` перемещена в `application/` в корне проекта
  - Обновлены все импорты с `services.application.*` на `application.*`
  - Это изменение улучшает структуру проекта, делая application-слой более явным и независимым от services

- **Перемещена директория domain в корень проекта**:
  - Директория `services/domain` перемещена в `domain/` в корне проекта
  - Обновлены все импорты с `services.domain.*` на `domain.*`
  - Это изменение улучшает структуру проекта, делая domain-слой более явным и независимым от services

- **Перемещена директория infrastructure в корень проекта**:
  - Директория `services/infrastructure` перемещена в `infrastructure/` в корне проекта
  - Обновлены все импорты с `services.infrastructure.*` на `infrastructure.*`
  - Обновлены внутренние импорты в `infrastructure/*/__init__.py` файлах
  - Это изменение улучшает структуру проекта, делая infrastructure-слой более явным и независимым от services

- **Перемещены директории base и clients в соответствии с архитектурой**:
  - Директория `services/base` перемещена в `shared/base/` в корне проекта
  - Директория `services/clients` перемещена в `infrastructure/clients/` в корне проекта
  - Обновлены все импорты с `services.base.*` на `shared.base.*`
  - Обновлены все импорты с `services.clients.*` на `infrastructure.clients.*`
  - Обновлены внутренние импорты в `infrastructure/clients/` и `shared/base/`
  - Это изменение улучшает структуру проекта: base классы находятся в shared (общий код), клиенты в infrastructure (внешние зависимости)

- **Обновлены протоколы для поддержки транзакций**:
  - Добавлен опциональный параметр `connection` в методы `IMetrics.increment_*()`
  - Добавлен опциональный параметр `connection` в метод `IUsageTracker.increment()`
  - Протоколы теперь поддерживают работу с транзакциями через опциональное соединение

- **DispatchExecutionService использует DatabaseOperationsService**:
  - Добавлен параметр `database_operations` в конструктор `DispatchExecutionService`
  - Автоматическое создание `DatabaseOperationsService`, если не передан
  - Метод `send_single_photo()` использует `record_dispatch_success()` для атомарной регистрации
  - Заменены прямые вызовы репозиториев на использование транзакционного сервиса
  - Обеспечена атомарность операций: регистрация отправки, инкремент счётчика, обновление метрик

- **Обновлен container.py для создания DatabaseOperationsService**:
  - Добавлено создание `DatabaseOperationsService` в `build_bot_services()`
  - `DatabaseOperationsService` передается в `DispatchExecutionService`
  - Все сервисы используют `MetricsRecorder` для единообразной работы с метриками

### Тесты

- **Добавлены тесты для DatabaseUnitOfWork**:
  - Тест успешного коммита транзакции через context manager
  - Тест отката транзакции при ошибке
  - Тест ручного управления транзакцией (begin/commit/rollback)
  - Тест получения соединения через property и get_connection()
  - Тест защиты от повторного начала транзакции

- **Добавлены тесты для DatabaseOperationsService**:
  - Тест успешной регистрации отправки (атомарность операций)
  - Тест отката транзакции при ошибке одной из операций
  - Тест регистрации неуспешной отправки
  - Тест работы без метрик

- **Обновлены тесты репозиториев**:
  - Добавлены тесты для работы с опциональным соединением в транзакциях
  - Тесты проверяют атомарность операций через DatabaseUnitOfWork

### Изменено

- **FallbackService использует DatabaseOperationsService**:
  - Добавлен параметр `database_operations` в конструктор `FallbackService`
  - Заменены прямые вызовы репозиториев на использование `record_dispatch_success()`
  - Обеспечена атомарность операций при регистрации fallback отправок
  - Добавлен fallback на прямые вызовы, если `DatabaseOperationsService` недоступен

- **Добавлено debug-логирование в DatabaseUnitOfWork**:
  - Логирование начала транзакции в `begin()`
  - Логирование успешного коммита в `commit()`
  - Логирование отката транзакции в `rollback()`
  - Улучшен мониторинг транзакций для отладки

- **Отложенное пересоздание кэша при ошибках сохранения**:
  - Добавлен метод `get_by_path()` в протокол `IImageStorage` и реализацию `ImageStorageService`
  - Реализован метод `rebuild_cache_from_storage()` в `ImageStorageUnitOfWork` с использованием `@retry_standard` для exponential retry
  - Добавлена очередь неудачных операций кэширования `_failed_cache_operations` для отложенного пересоздания
  - Реализована фоновая задача `_rebuild_failed_caches_loop()` через `asyncio.create_task` для неблокирующего пересоздания кэша
  - Автоматическое добавление операций в очередь при ошибке сохранения в кэш (но успешном сохранении в хранилище)
  - Улучшенная надёжность: кэш пересоздаётся даже при временных сбоях (пул исчерпан, таймауты)
  - Добавлены unit-тесты для `ImageStorageUnitOfWork` в `tests/test_services/test_image_storage_unit_of_work.py`
  - Обновлена документация в `ImageStorageUnitOfWork` с описанием отложенного пересоздания кэша

- **ImageStorageUnitOfWork для управления сохранением изображений**:
  - Создан сервис `ImageStorageUnitOfWork` в `services/application/image_storage_unit_of_work.py`
  - Реализован паттерн Unit of Work для группировки операций сохранения изображений
  - Добавлен класс `ImageSaveOperation` для представления операций сохранения
  - Методы: `save_image()`, `commit()`, `rollback()`, `clear()`
  - Используется стратегия компенсационных действий для улучшения согласованности данных
  - Приоритет сохранения: сначала хранилище (критичное), затем кэш (второстепенное)

### Добавлено

- **Метод delete() в IImageStorage для удаления файлов из хранилища**:
  - Добавлен метод `delete()` в протокол `IImageStorage`
  - Реализован метод `delete()` в `ImageStorageService`
  - Метод доступен для использования, но не вызывается в `ImageStorageUnitOfWork.rollback()` (хранилище имеет приоритет над кэшем)

### Изменено

- **Рефакторинг ImageService для использования ImageStorageUnitOfWork**:
  - Обновлён конструктор `ImageService` для принятия `ImageStorageUnitOfWork`
  - Заменено прямое сохранение в кэш и хранилище на использование `ImageStorageUnitOfWork.save_image()`
  - Улучшена обработка ошибок сохранения с компенсационными действиями через `rollback()`
  - Исправлена синтаксическая ошибка в блоке обработки исключений при генерации изображений
  - Упрощён код сохранения: логика инкапсулирована в UnitOfWork
  - Обновлён `container.py` для создания `ImageStorageUnitOfWork` и передачи его в `ImageService`

- **APIStatusService для инкапсуляции проверки статуса API**:
  - Создан сервис `APIStatusService` в `services/application/api_status_service.py`
  - Сервис инкапсулирует логику проверки статуса различных API (Kandinsky, GigaChat)
  - Добавлены типизированные классы `ImageAPIStatus` и `TextAPIStatus` для результатов проверки
  - Методы: `check_image_api_status()`, `check_text_api_status()`, `get_image_models()`, `get_text_models()`
  - Единый интерфейс для получения статуса всех API с обработкой ошибок
  - Автоматическое сохранение списков моделей в хранилище при проверке статуса

### Изменено

- **Рефакторинг AdminDashboardService для использования APIStatusService**:
  - Обновлён конструктор `AdminDashboardService` для принятия `APIStatusService` вместо клиентов
  - Удалены прямые зависимости от `ITextToImageClient`, `ITextToTextClient` и `IModelsRepo`
  - Удалены свойства `image_client` и `text_client` (breaking change)
  - Упрощены методы `build_status_message()` и `build_models_list_message()` для использования `APIStatusService`
  - Улучшена инкапсуляция: детали работы с клиентами скрыты в `APIStatusService`
  - Обновлён `container.py` для создания `APIStatusService` и передачи его в `AdminDashboardService`

- **Обновление ModelHandlers для получения клиентов из контейнеров**:
  - Обновлён `ModelHandlers` для получения клиентов напрямую из контейнеров вместо свойств `AdminDashboardService`
  - Используются `get_image_client_container()` и `get_text_client_container()` для доступа к клиентам

- **Перенос логики форматирования из AdminDashboardService в билдеры**:
  - Обновлён `StatusData` для передачи сырых данных вместо отформатированных строк
  - Добавлены методы форматирования в `StatusMessageBuilder`: `_format_usage_info()`, `_format_chats_info()`, `_format_metrics_text()`, `_format_kandinsky_current()`, `_format_gigachat_current()`
  - Улучшено разделение ответственностей: сервис собирает данные, билдеры форматируют
  - Удалена константа `PERCENT_MULTIPLIER` из AdminDashboardService (перенесена в StatusMessageBuilder)
  - Обновлена документация для отражения новой структуры

### Добавлено

- **TargetPreparationService для подготовки целевых чатов**:
  - Создан сервис `TargetPreparationService` в `services/application/target_preparation_service.py`
  - Сервис инкапсулирует логику подготовки целевых чатов для рассылки
  - Методы: `prepare_targets()`, `is_already_dispatched_for_all()`
  - Выделена ответственность за работу с чатами и dispatch registry

- **DispatchExecutionService для выполнения отправки сообщений**:
  - Создан сервис `DispatchExecutionService` в `services/application/dispatch_execution_service.py`
  - Сервис инкапсулирует логику отправки сообщений в целевые чаты
  - Методы: `send_single_photo()`, `send_to_targets()`
  - Выделена ответственность за отправку, регистрацию и метрики

- **FallbackService для обработки fallback сценариев**:
  - Создан сервис `FallbackService` в `services/application/fallback_service.py`
  - Сервис инкапсулирует логику обработки ошибок и fallback сценариев
  - Методы: `send_fallback_to_targets()`, `handle_generation_failure()`, `handle_unexpected_error()`
  - Выделена ответственность за обработку ошибок и fallback логику

### Изменено

- **Рефакторинг DispatchService для использования выделенных сервисов**:
  - Обновлён конструктор `DispatchService` для принятия новых сервисов
  - Упрощён метод `send_wednesday_frog()` для координации между сервисами
  - Удалены методы, перенесённые в другие сервисы: `_prepare_targets()`, `_already_dispatched_for_all()`, `_send_single_photo()`, `_send_to_targets()`, `_send_fallback_to_targets()`, `_handle_generation_failure()`, `_handle_unexpected_error()`
  - Удалён метод `_generate_image()` (заменён прямым вызовом `image_service.generate_frog_image()`)
  - Упрощена структура сервиса: с ~535 строк до ~200 строк
  - Улучшено соблюдение SRP: сервис фокусируется только на координации
  - Обновлён `container.py` для создания новых сервисов и передачи их в DispatchService

- **Обновление документации DispatchService**:
  - Обновлены docstrings в DispatchService для отражения новой структуры
  - Добавлено описание координации между сервисами
  - Уточнено, что сервис теперь фокусируется только на координации

### Добавлено

- **CaptionService для работы с подписями к изображениям**:
  - Создан доменный сервис `CaptionService` в `services/domain/caption_service.py`
  - Добавлен протокол `ICaptionProvider` в `services/protocols.py`
  - Сервис инкапсулирует бизнес-логику выбора подписей для сгенерированных изображений
  - Методы: `get_random_caption()`, `get_all_captions()`, `has_captions()`
  - Валидация пустого списка подписей при инициализации

### Изменено

- **Перенос retry логики в ImageGenerationService**:
  - Добавлен декоратор `@retry_standard()` к методу `generate()` в `ImageGenerationService`
  - Retry логика теперь находится в domain слое, а не в application слое
  - Улучшено соблюдение принципа Single Responsibility Principle

- **Обновление ImageService для использования CaptionService**:
  - Заменён параметр `captions` на `caption_service: CaptionService | None` в конструкторе
  - Удалён метод `_get_random_caption()` из ImageService
  - Обновлено использование подписей для использования CaptionService
  - Удалён импорт `random` из ImageService
  - Обновлён `container.py` для создания CaptionService из ImageConfig.CAPTIONS

- **Удаление retry логики из ImageService**:
  - Удалён цикл retry из метода `generate_frog_image()`
  - Удалён параметр `max_retries` из конструктора ImageService
  - Удалён импорт `asyncio` из ImageService
  - Retry логика теперь полностью находится в ImageGenerationService (domain слой)
  - Упрощена обработка ошибок генерации в ImageService

- **Добавление тестов для CaptionService**:
  - Создан файл `tests/test_services/test_domain_caption_service.py` с unit-тестами
  - Тесты покрывают все методы CaptionService: `get_random_caption()`, `get_all_captions()`, `has_captions()`
  - Тесты проверяют валидацию пустого списка подписей
  - Тесты проверяют работу с кортежами и списками подписей

- **Обновление документации ImageService**:
  - Обновлены docstrings в ImageService для отражения изменений
  - Добавлено упоминание CaptionService в описании координации
  - Обновлено описание последовательности генерации изображений
  - Уточнено, что retry логика находится в ImageGenerationService

### Добавлено

- **Документация по добавлению новых эндпоинтов в HTTP-клиентах**:
  - Создан файл `docs/clients/adding_endpoints.md` с руководством по добавлению новых методов
  - Документированы паттерны использования: простой GET/POST с JSON, кастомная обработка, FormData, кастомные заголовки и таймауты
  - Добавлен checklist для добавления нового метода
  - Добавлены примеры улучшений (до/после рефакторинга)
  - Добавлены примеры использования в docstrings методов базового класса `BaseHTTPClient`
  - Добавлены шаблоны кода в виде комментариев в `KandinskyClient` и `GigaChatTextClient` для быстрого добавления новых методов

- **Helper-методы для парсинга ответов и обработки ошибок в BaseHTTPClient**:
  - Метод `_parse_json_response()` для парсинга JSON с валидацией статуса
  - Метод `_safe_parse_json()` для безопасного парсинга JSON без проверки статуса
  - Метод `_get_response_text()` для получения текста ответа с ограничением длины
  - Методы `_get_json()` и `_post_json()` для удобного паттерна "запрос + парсинг JSON"
  - Улучшенная обработка сетевых ошибок в методах `_get()` и `_post()` с преобразованием в `NetworkError`

### Изменено

- **Рефакторинг конфигурации fallback промптов**:
  - Перенесён dataclass `PromptFallbackConfig` из `services/domain/prompt_fallback_config.py` в `utils/config.py`
  - Обновлены импорты в `services/domain/prompt_generation.py` и `services/container.py`
  - Удалён избыточный модуль `services/domain/prompt_fallback_config.py`
  - Конфигурация теперь находится вместе с другими конфигурационными классами

- **Упрощение обработки ошибок в методах клиентов**:
  - Удалены избыточные обработчики сетевых ошибок (TimeoutError, ClientConnectorError, ClientError) из методов клиентов
  - Сетевые ошибки теперь автоматически обрабатываются в базовом классе BaseHTTPClient и преобразуются в NetworkError
  - Упрощены методы `generate()`, `check_api_status()`, `set_model()`, `_get_pipeline_id()`, `_start_generation()` в KandinskyClient
  - Упрощены методы `generate()`, `get_available_models()`, `_get_access_token()` в GigaChatTextClient
  - Устранено дублирование логики обработки сетевых ошибок

- **Рефакторинг клиентов для использования helper-методов**:
  - `KandinskyClient._fetch_pipelines()` теперь использует `_get_json()` вместо ручного парсинга
  - `KandinskyClient._start_generation()` использует `_parse_json_response()` для парсинга JSON
  - `KandinskyClient._wait_for_generation()` использует `_parse_json_response()` вместо `_validate_response()` + `response.json()`
  - `GigaChatTextClient.generate()` использует `_parse_json_response()` для парсинга JSON
  - `GigaChatTextClient.get_available_models()` использует `_parse_json_response()` для парсинга JSON
  - `GigaChatTextClient._get_access_token()` использует `_parse_json_response()` для парсинга JSON
  - Устранено дублирование логики парсинга ответов во всех методах клиентов

### Изменено

- **Устранение дублирования кода: выделение общей логики HTTP-запросов**:
  - Создан базовый класс `BaseHTTPClient` с общей логикой HTTP-запросов
  - Методы `_get()` и `_post()` для выполнения GET и POST запросов с retry логикой
  - Метод `_validate_response()` для единообразной валидации ответов API
  - Метод `_build_url()` для формирования полных URL из базового URL и эндпоинтов
  - `KandinskyClient` и `GigaChatTextClient` теперь наследуются от `BaseHTTPClient`
  - Устранено дублирование кода формирования URL, выполнения запросов и обработки ответов
  - Добавлены константы эндпоинтов в `KandinskyClient` для улучшения читаемости
  - Создан helper-метод `_fetch_pipelines()` в `KandinskyClient` для переиспользования логики получения pipelines
  - Упрощено добавление новых эндпоинтов и улучшена поддерживаемость кода
  - Удалены все дублирующиеся функции типа `_fetch_pipelines_status()`, `_fetch_pipelines_for_set_model()` и т.д.

- **Унификация обработки ошибок во всех методах клиентов**:
  - Метод `get_available_models()` теперь пробрасывает доменные исключения вместо возврата пустого/fallback списка
  - Все методы клиентов используют единый подход к обработке ошибок через доменные исключения
  - Успешные результаты возвращаются без Optional (конкретные типы)
  - Создан модуль `services/clients/error_handling.py` с helper-функциями `log_client_error()` и `should_retry()`
  - Обновлены интерфейсы `ITextToImageClient` и `ITextToTextClient` с полной документацией исключений
  - Обновлен вызывающий код для единообразной обработки ошибок через try/except
  - Улучшена согласованность интерфейса клиентов и упрощено тестирование

- **Рефакторинг методов проверки статуса: проброс исключений вместо кортежей с ошибками**:
  - Созданы типизированные структуры `APIStatusResult` и `SetModelResult` для результатов проверки статуса и установки моделей
  - Обновлены интерфейсы `ITextToImageClient` и `ITextToTextClient` для использования новых типов возвращаемых значений
  - Методы `check_api_status()` и `set_model()` теперь пробрасывают доменные исключения (`AuthenticationError`, `RateLimitError`, `NetworkError`, `APIError`) вместо возврата кортежей с ошибками
  - Обновлены `KandinskyClient` и `GigaChatTextClient` для проброса исключений при HTTP ошибках
  - Обновлены контейнеры клиентов (`ImageClientContainer`, `TextClientContainer`) для проброса исключений
  - Обновлен вызывающий код (`AdminDashboardService`, `ModelHandlers`) для обработки исключений через try/except
  - Упрощен и улучшен код обработки ошибок в вызывающих методах
  - Улучшена типобезопасность возвращаемых значений через dataclass вместо кортежей

### Добавлено

- **Типизация Request/Response через Pydantic модели для HTTP-клиентов**:
  - Создана структура `services/clients/models/` для хранения Pydantic моделей
  - Добавлены модели для Kandinsky API (KandinskyPipelineResponse, KandinskyGenerationRequest, KandinskyGenerationParams, KandinskyGenerationStartResponse, KandinskyStatus, KandinskyStatusResponse, KandinskyResult)
  - Добавлены модели для GigaChat API (GigaChatTokenResponse, GigaChatCompletionResponse, GigaChatMessage, GigaChatChoice, GigaChatModelsListResponse, GigaChatModelInfo)
  - Все модели поддерживают валидацию структуры данных и типизацию
  - Модели документированы через docstrings

### Изменено

- **Устранение частичной типизации: проверка соответствия docstrings и type hints**:
  - Обновлены docstrings для всех методов клиентов - они описывают поведение, а не дублируют информацию из type hints
  - Добавлена типизация констант через `Final` для всех констант в клиентах (HTTP_STATUS_*, MAX_*, STATUS_*, TOKEN_*, DEFAULT_*, MAX_ERROR_*, AUTH_KEY_*)
  - Добавлена опция `warn_no_return = true` в конфигурацию mypy для строгой проверки возвращаемых значений
  - Все методы имеют полные type hints, mypy может статически проверять типы
  - Docstrings синхронизированы с type hints через статическую проверку mypy
  - Улучшено автодополнение в IDE за счет полной типизации
  - Обновлен `docs/TYPING_GUIDE.md` с разделом о правильном использовании docstrings и type hints

- **KandinskyClient: использование Pydantic моделей вместо dict[str, Any]**:
  - Обновлен метод `_get_pipeline_id()` для использования `KandinskyPipelineResponse`
  - Обновлен метод `_start_generation()` для использования `KandinskyGenerationRequest` и `KandinskyGenerationStartResponse`
  - Обновлен метод `_wait_for_generation()` для использования `KandinskyStatusResponse` и `KandinskyStatus` enum
  - Обновлены методы `check_api_status()` и `set_model()` для использования `KandinskyPipelineResponse`
  - Добавлена обработка ошибок валидации через `ValidationError`
  - Удалены ручные проверки и валидации через `.get()` и `isinstance()`
  - Типобезопасный доступ к полям ответов API

- **GigaChatTextClient: использование Pydantic моделей вместо dict[str, Any]**:
  - Обновлен метод `_get_access_token()` для использования `GigaChatTokenResponse`
  - Обновлен метод `generate_prompt()` для использования `GigaChatCompletionResponse`
  - Обновлен метод `get_available_models()` для использования `GigaChatModelsListResponse` и `GigaChatModelInfo`
  - Добавлена обработка ошибок валидации через `ValidationError`
  - Поддержка различных форматов ответов API (dict с data/models или list)
  - Удалены ручные проверки и валидации через `.get()` и `isinstance()`
  - Типобезопасный доступ к полям ответов API

- **Вынос захардкоженных таймаутов в конфигурацию через HttpTimeoutConfig**:
  - Создан универсальный `HttpTimeoutConfig` dataclass для всех HTTP-таймаутов (total, connect, sock_read)
  - Добавлен метод `create_http_timeout()` в класс `Config` для создания таймаутов из переменных окружения
  - Обновлен `KandinskyConfig` для использования `HttpTimeoutConfig` (generation_timeout, check_timeout)
  - Обновлен `GigaChatConfig` для использования `HttpTimeoutConfig` (prompt_timeout, models_timeout, token_timeout)
  - Удалены константы таймаутов из `KandinskyClient` (TIMEOUT_GENERATION_*, TIMEOUT_CHECK_*)
  - Удалены константы таймаутов из `GigaChatTextClient` (TIMEOUT_TOKEN_SECONDS, TIMEOUT_PROMPT_SECONDS, TIMEOUT_MODELS_SECONDS)
  - Обновлены клиенты для использования таймаутов из конфига через метод `to_client_timeout()`
  - Удалены захардкоженные значения connect и sock_read из кода GigaChat
  - Добавлены переменные окружения для настройки таймаутов (KANDINSKY_GENERATION_TIMEOUT_*, KANDINSKY_CHECK_TIMEOUT_*, GIGACHAT_PROMPT_TIMEOUT_*, GIGACHAT_MODELS_TIMEOUT_*, GIGACHAT_TOKEN_TIMEOUT_*)
  - Единообразная структура таймаутов для всех HTTP-клиентов
  - Упрощено тестирование (можно подменить таймауты в конфиге)
  - Поддержка разных окружений с разными таймаутами без изменения кода
  - **BREAKING CHANGE**: Таймауты теперь обязательные поля в `KandinskyConfig` и `GigaChatConfig`

- **Вынос захардкоженных URL в конфигурацию клиентов**:
  - Добавлено поле `base_url` в `KandinskyConfig` для настройки базового URL через переменные окружения
  - Добавлено свойство `kandinsky_base_url` в класс `Config`
  - Обновлен `KandinskyClient` для использования `config.base_url` вместо захардкоженного значения
  - Добавлено поле `models_url` в `GigaChatConfig` для настройки URL получения списка моделей
  - Добавлено свойство `gigachat_models_url` в класс `Config`
  - Обновлен `GigaChatTextClient` для использования `config.models_url` вместо захардкоженного значения
  - Добавлены переменные окружения `KANDINSKY_BASE_URL` и `GIGACHAT_MODELS_URL`
  - Упрощено тестирование (можно подменить URL в конфиге)
  - Поддержка разных окружений без изменения кода

- **Вынос настроек circuit breaker в конфигурацию (CircuitBreakerConfig)**:
  - Создан dataclass `CircuitBreakerConfig` для централизованного управления настройками circuit breaker
  - Добавлен метод `get_circuit_breaker_config()` в класс `Config`
  - Обновлено создание `CircuitBreakerService` в `services/container.py` для использования конфига
  - Добавлены Prometheus метрики `circuit_breaker_state` и `circuit_breaker_failures` для мониторинга
  - Обновлен `CircuitBreakerService` для автоматического обновления метрик при изменении состояния
  - Добавлены переменные окружения `CIRCUIT_BREAKER_THRESHOLD`, `CIRCUIT_BREAKER_WINDOW`, `CIRCUIT_BREAKER_COOLDOWN`
  - Улучшена наблюдаемость состояния circuit breaker через метрики Prometheus

- **Вынос настроек retry в конфигурацию (RetryConfig)**:
  - Создан dataclass `RetryConfig` для централизованного управления настройками retry
  - Добавлен метод `get_retry_config()` в класс `Config`
  - Обновлены декораторы `retry_standard`, `retry_critical`, `retry_optional` для использования `RetryConfig`
  - Добавлена возможность переопределения параметров через аргументы декораторов
  - Добавлены переменные окружения `RETRY_STANDARD_MAX_ATTEMPTS`, `RETRY_CRITICAL_MAX_ATTEMPTS`, `RETRY_OPTIONAL_MAX_ATTEMPTS`
  - Обновлен `RetryConfig.from_config()` для чтения напрямую из переменных окружения
  - Обновлен `retry_with_logging` для использования `RetryConfig`
  - **BREAKING CHANGE**: Удалены старые свойства `retry_max_attempts`, `retry_multiplier`, `retry_min_wait`, `retry_max_wait` из класса `Config`
  - Используйте `config.get_retry_config()` для получения настроек retry

- **Dependency Injection для Redis клиента**:
  - Сделан параметр `redis_client` обязательным во всех сервисах Redis (`RedisBackendService`, `PromptCache`, `UserStateCache`, `RateLimiter`, `CircuitBreakerService`)
  - Убран fallback на глобальный клиент через `get_redis()` в конструкторах сервисов
  - Обновлен `services/container.py` для явной передачи Redis клиента при создании сервисов
  - Обновлены `bot/support_bot.py` и тесты для передачи Redis клиента явно
  - Исправлены импорты в `tests/conftest.py` для использования новых путей репозиториев
  - Обновлен тест `test_circuit_breaker_opens_after_threshold` для корректной обработки исключения `CircuitBreakerOpen`
  - Улучшена тестируемость и изоляция тестов (нет зависимости от глобального состояния)

- **Перенос оставшихся репозиториев в services/infrastructure/repositories/**:
  - Перенесены `AdminsRepo` из `utils/admins_repo.py` в `services/infrastructure/repositories/admins_repo.py`
  - Перенесены `ChatsRepo` из `utils/chats_repo.py` в `services/infrastructure/repositories/chats_repo.py`
  - Перенесены `ModelsRepo` из `utils/models_repo.py` в `services/infrastructure/repositories/models_repo.py`
  - Обновлен `services/infrastructure/repositories/__init__.py` для экспорта всех репозиториев
  - Обновлены все импорты в коде и тестах для использования новых путей
  - Удалены старые файлы из `utils/`
  - Все репозитории теперь находятся в правильном архитектурном слое согласно принципам чистой архитектуры

- **Удаление устаревшего параметра storage_path из репозиториев**:
  - Удален параметр `storage_path` из конструкторов всех репозиториев (`ChatsRepo`, `AdminsRepo`, `ModelsRepo`, `UsageTracker`, `DispatchRegistry`, `Metrics`)
  - Параметр был оставлен для обратной совместимости после миграции с JSON-файлов на PostgreSQL, но не использовался
  - Обновлены все места создания репозиториев в коде и тестах
  - Обновлена документация в `docs/TESTING_GUIDE.md`

- **Удаление обратной совместимости для репозиториев**:
  - Параметр `pool` теперь обязателен во всех репозиториях (`PromptsRepo`, `ImagesRepo`, `ChatsRepo`, `AdminsRepo`, `ModelsRepo`, `UsageTracker`, `DispatchRegistry`, `Metrics`)
  - Обновлены функции `build_bot_services()` и `build_bot()` для обязательной передачи пула
  - Обновлены все тесты для передачи тестового пула из фикстуры `async_postgres_pool`
  - Обновлены fallback в клиентах (`KandinskyClient`, `GigaChatTextClient`) для использования `get_postgres_pool()` при создании `ModelsRepo`
  - Удалены опциональные параметры и fallback логика из конструкторов репозиториев

- **Dependency Injection для пула PostgreSQL и мониторинг соединений**:
  - Добавлен dataclass `PoolMetrics` и функция `get_pool_metrics()` в `utils/postgres_client.py`
  - Обновлены репозитории для поддержки DI: `PromptsRepo`, `ImagesRepo`, `ChatsRepo`, `AdminsRepo`, `ModelsRepo`
  - Обновлены классы для поддержки DI: `UsageTracker`, `DispatchRegistry`, `Metrics`
  - Обновлен `services/container.py` для передачи пула в репозитории через DI
  - Добавлены Prometheus метрики для пула PostgreSQL: `postgres_pool_size`, `postgres_pool_idle`, `postgres_pool_active`, `postgres_pool_max`
  - Добавлена функция `update_pool_metrics()` для обновления метрик пула
  - Интегрировано обновление метрик в healthcheck с логированием предупреждений при высоком использовании пула (>90%)
  - Сохранена обратная совместимость: все репозитории имеют параметр `pool: asyncpg.Pool | None = None` с fallback на глобальный пул
  - Улучшена тестируемость: можно передавать тестовый пул в репозитории для изоляции тестов

- **Добавление context manager для HTTP клиентов**:
  - Добавлены методы `__aenter__` и `__aexit__` в `KandinskyClient` для поддержки async context manager
  - Добавлены методы `__aenter__` и `__aexit__` в `GigaChatTextClient` для поддержки async context manager
  - Обновлены тесты для использования context manager вместо явного вызова `aclose()`
  - Добавлены unit-тесты для проверки корректной работы context manager
  - Гарантированное закрытие ресурсов даже при исключениях
  - Упрощённое использование клиентов в тестах и временных операциях

- **Перенос репозиториев из utils/ в services/infrastructure/repositories/**:
  - Создана директория `services/infrastructure/repositories/` для репозиториев
  - Перенесены `ImagesRepo` и `ImageRecord` из `utils/images_repo.py` в `services/infrastructure/repositories/images_repo.py`
  - Перенесены `PromptsRepo` и `PromptRecord` из `utils/prompts_repo.py` в `services/infrastructure/repositories/prompts_repo.py`
  - Обновлены импорты в `services/protocols.py` для использования новых путей
  - Обновлены импорты в `services/container.py` для использования новых путей
  - Обновлены импорты в тестах `test_images_repo.py` и `test_prompts_repo.py`
  - Обновлены пути в monkeypatch для тестов
  - Удалены старые файлы `utils/images_repo.py` и `utils/prompts_repo.py`
  - Репозитории теперь находятся в правильном архитектурном слое согласно принципам чистой архитектуры

- **Маппинг HTTP-ошибок в доменные исключения для клиентов**:
  - Создан модуль `services/clients/exceptions.py` с доменными исключениями (`ClientError`, `AuthenticationError`, `RateLimitError`, `NetworkError`, `APIError`)
  - Добавлена функция `map_http_status_to_exception()` для маппинга HTTP статусов в доменные исключения
  - Обновлен `KandinskyClient`: методы `generate()`, `_get_pipeline_id()`, `_start_generation()`, `_wait_for_generation()` теперь пробрасывают исключения вместо возврата `None`
  - Обновлен `GigaChatTextClient`: методы `generate()` и `_get_access_token()` теперь пробрасывают исключения вместо возврата `None`
  - Обновлены интерфейсы `ITextToImageClient` и `ITextToTextClient`: удален `Optional` из возвращаемых типов методов `generate()`, добавлена документация исключений в docstrings
  - Обновлен `ImageGenerationService`: добавлена специфичная обработка исключений клиентов с маппингом в доменные исключения
  - Обновлен `PromptGenerationService`: добавлена обработка исключений клиентов с возвратом `None` для использования fallback промпта
  - Добавлен экспорт исключений в `services/clients/__init__.py` для удобного импорта
  - **BREAKING CHANGE**: Методы клиентов больше не возвращают `None`, а пробрасывают исключения. Вызывающий код должен обрабатывать исключения через try/except

- **Добавление валидации и нормализации промптов в ImageGenerationService**:
  - Добавлены константы `MIN_PROMPT_LENGTH` и `MAX_PROMPT_LENGTH` для валидации промптов
  - Добавлен метод `_normalize_prompt()` для нормализации промптов (удаление пробелов по краям и лишних пробелов внутри)
  - Добавлен метод `_validate_prompt()` для валидации промптов (проверка длины и непустоты)
  - Интегрирована валидация и нормализация в метод `generate()` перед вызовом клиента
  - Обновлена документация класса и методов для отражения новой функциональности
  - Добавлены unit-тесты для всех новых методов и сценариев
  - `ImageGenerationService` теперь содержит бизнес-логику валидации и нормализации на уровне domain
  - Инкапсулированы бизнес-правила генерации (ограничения длины промпта)
  - Повышена надёжность за счёт отклонения невалидных промптов до обращения к API

- **Удаление зависимости domain слоя от utils.config**:
  - Обновлен `services/container.py` для прямого создания `PromptFallbackConfig` из `ImageConfig`
  - Удален метод `from_image_config()` из `services/domain/prompt_fallback_config.py`
  - `PromptFallbackConfig` теперь является чистым dataclass без методов создания
  - Создание конфигурации перенесено в Composition Root (`container.py`)
  - Domain слой больше не зависит от `utils.config` через метод `from_image_config()`
  - Улучшена изоляция domain слоя от инфраструктуры конфигурации согласно принципу Dependency Inversion

- **Перенос протоколов ITextToImageClient и ITextToTextClient в services/protocols.py**:
  - Добавлены протоколы `ITextToImageClient` и `ITextToTextClient` в `services/protocols.py`
  - Протоколы используют декоратор `@runtime_checkable` для проверки типов в runtime
  - Обновлен `services/clients/__init__.py` для реэкспорта протоколов из `services.protocols`
  - Обеспечена обратная совместимость для кода, использующего импорт через `services.clients`
  - Обновлены импорты в `services/domain/image_generation.py` для использования `services.protocols`
  - Обновлены импорты в `services/domain/prompt_generation.py` для использования `services.protocols`
  - Обновлены импорты в клиентах (`gigachat_text.py`, `factory.py`, `kandinsky.py`) для использования `services.protocols`
  - Обновлены импорты в `services/container.py` и `services/application/admin_dashboard_service.py` для использования `services.protocols`
  - Обновлены импорты в контейнерах клиентов (`image_client_container.py`, `text_client_container.py`) для использования `services.protocols`
  - Обновлены импорты в тестах для использования `services.protocols`
  - Удалены все прямые импорты из `services.clients.interfaces`
  - Удален файл `services/clients/interfaces.py` после переноса всех протоколов
  - Domain слой теперь зависит только от абстракций в `services.protocols`, а не от модуля `services.clients`
  - Улучшена изоляция domain слоя от инфраструктуры согласно принципу Dependency Inversion

- **Унификация использования протокола IMetrics**:
  - Добавлен метод `get_summary()` в протокол `IMetrics` в `services/protocols.py`
  - Добавлены недостающие методы `increment_cache_hit()` и `record_circuit_breaker_trip()` в класс `Metrics` для полного соответствия протоколу
  - Добавлен метод `get_summary()` в `MetricsRecorder` для полной реализации протокола
  - Заменены типы параметров с `Metrics` на `IMetrics` в `BotServices`, `DispatchService`, `AdminDashboardService` и `build_admin_dashboard_service()`
  - Обновлены импорты для использования протокола `IMetrics` вместо конкретного класса `Metrics`
  - Улучшена абстракция и тестируемость через использование протоколов

- **Централизованное закрытие ресурсов в BotServices.cleanup()**:
  - Добавлено закрытие Redis соединений через `close_redis()` в `BotServices.cleanup()`
  - Добавлено закрытие PostgreSQL pool через `close_postgres_pool()` в `BotServices.cleanup()`
  - Обновлен `_cleanup()` в `main.py` для вызова `services.cleanup()` при остановке ботов
  - Добавлен гарантированный вызов cleanup через `atexit` handler в `BotRunner` для случаев аварийного завершения
  - Устранены потенциальные утечки соединений при завершении приложения
  - Улучшена надежность освобождения ресурсов

- **Асинхронизация метода load_image_bytes в ImagesRepo**:
  - Метод `load_image_bytes()` в `utils/images_repo.py` теперь асинхронный
  - Используется `asyncio.to_thread()` для неблокирующего чтения файлов
  - Обновлен протокол `IImageRepo` в `services/protocols.py` для асинхронного метода
  - Обновлены вызовы в `ImageCacheService` с добавлением `await`
  - Устранена блокирующая операция I/O в асинхронном контексте

- **Внедрение протокола IModelsRepo для ModelsRepo**:
  - Создан протокол `IModelsRepo` в `services/protocols.py` для абстракции репозитория моделей
  - `GigaChatTextClient` и `KandinskyClient` теперь принимают `IModelsRepo` через dependency injection вместо создания `ModelsRepo` напрямую
  - `AdminDashboardService` теперь использует протокол `IModelsRepo` вместо конкретного класса `ModelsRepo`
  - Фабрики `create_image_client()` и `create_text_client()` принимают `models_repo` для передачи в клиенты
  - В `container.py` создается единый экземпляр `ModelsRepo` и передается во все сервисы через DI
  - Улучшена тестируемость и соблюдение принципов Dependency Injection

- **Централизация конфигураций клиентов в config.py**:
  - Классы `GigaChatConfig`, `KandinskyConfig` и `AppSettings` перенесены из отдельных модулей в `utils/config.py`
  - Все конфигурации теперь находятся в одном месте, аналогично `ImageConfig` и `SchedulerConfig`
  - Удалены файлы `services/clients/gigachat_config.py`, `services/clients/kandinsky_config.py` и `services/app_settings.py`
  - Обновлены все импорты для использования классов из `utils/config`
  - Улучшена централизация конфигурации и уменьшено количество модулей

- **Рефакторинг зависимостей от config в container.py**:
  - Функции `_create_clients()`, `build_image_stack()`, `build_bot_services()` и `build_bot()` теперь принимают `config` как явный параметр
  - Удалена скрытая зависимость от глобального `config` в `services/container.py`
  - Обновлены вызовы `build_bot()` в `main.py` и `services/infrastructure/celery/context.py` для передачи `config`
  - Улучшена тестируемость и явность зависимостей согласно принципам Dependency Injection

### Добавлено

- **Централизованное управление жизненным циклом ресурсов в BotServices**:
  - Добавлен метод `cleanup()` в класс `BotServices` для централизованного закрытия всех ресурсов
  - Метод закрывает `ImageClientContainer` и `TextClientContainer` через `aclose()`
  - Обеспечивает единую точку управления жизненным циклом ресурсов
  - Улучшает архитектуру и расширяемость для будущих ресурсов (Redis, PostgreSQL и т.д.)
  - `WednesdayBot.stop()` теперь использует `services.cleanup()` вместо прямых вызовов контейнеров
  - Удален метод `aclose()` из `WednesdayBot` - cleanup теперь управляется через `BotServices`
  - `shutdown_services()` в Celery контексте использует `bot.services.cleanup()` с fallback на прямые вызовы

### Изменено

- **Переиспользование aiohttp.ClientSession в KandinskyClient**:
  - Сессия создается в `__init__` один раз для переиспользования во всех методах
  - Timeout и connector сохраняются как поля класса
  - Методы `generate()`, `check_api_status()`, `set_model()` используют переиспользуемую сессию
  - Удалены все `async with aiohttp.ClientSession(...)` из методов
  - Для методов с меньшими таймаутами timeout передается явно в запросы
  - Реализован метод `aclose()` для закрытия сессии и освобождения ресурсов
  - Обновлены тесты для проверки создания сессии в `__init__`
  - Добавлен тест для метода `aclose()`
  - Улучшена производительность за счет connection pooling
  - Единообразие с подходом `GigaChatTextClient`

### Добавлено

- **Создание протоколов IUsageTracker и IChatsRepo**:
  - Добавлены протоколы `IUsageTracker` и `IChatsRepo` в `services/protocols.py`
  - Протоколы определяют интерфейсы для трекера использования и репозитория чатов
  - `IUsageTracker` содержит методы: `increment()`, `get_limits_info()`, `can_use_frog()`, `set_frog_threshold()`, `set_month_total()`, свойство `monthly_quota`
  - `IChatsRepo` содержит методы: `list_chat_ids()`, `add_chat()`, `remove_chat()`
  - Соответствуют принципу Dependency Inversion (DIP)

### Изменено

- **Рефакторинг AdminDashboardService для использования протоколов**:
  - Заменены типы параметров конструктора с конкретных классов на протоколы `IUsageTracker` и `IChatsRepo`
  - Удалены прямые импорты `UsageTracker` и `ChatsRepo` из модуля
  - Application слой больше не зависит от конкретных реализаций из `utils/`
  - Соответствует принципу Dependency Inversion (DIP)

- **Рефакторинг DispatchService для использования протоколов**:
  - Заменены типы параметров конструктора с конкретных классов на протоколы `IUsageTracker` и `IChatsRepo`
  - Удалены прямые импорты `UsageTracker` и `ChatsRepo` из модуля
  - Application слой больше не зависит от конкретных реализаций из `utils/`
  - Соответствует принципу Dependency Inversion (DIP)

- **Рефакторинг BotServices для использования протоколов**:
  - Заменены типы полей dataclass с конкретных классов на протоколы `IUsageTracker` и `IChatsRepo`
  - Удалены прямые импорты `UsageTracker` и `ChatsRepo` из модуля
  - Контейнер зависимостей использует протоколы для типизации
  - Соответствует принципу Dependency Inversion (DIP)

- **Создание протоколов IImageRepo и IPromptRepo**:
  - Добавлены протоколы `IImageRepo` и `IPromptRepo` в `services/protocols.py`
  - Протоколы определяют интерфейсы для репозиториев изображений и промптов в БД
  - Используют TYPE_CHECKING для импорта типов ImageRecord и PromptRecord
  - Соответствуют принципу Dependency Inversion (DIP)

### Изменено

- **Рефакторинг ImageCacheService для использования протоколов**:
  - Заменены типы параметров конструктора с конкретных классов на протоколы `IImageRepo` и `IPromptRepo`
  - Удалены прямые импорты `ImagesRepo` и `PromptsRepo` из модуля
  - Импорты конкретных классов перенесены внутрь `__init__` для fallback-создания
  - Infrastructure слой больше не зависит от конкретных реализаций из `utils/`
  - Соответствует принципу Dependency Inversion (DIP)

- **Обновление container.py для передачи репозиториев в ImageCacheService**:
  - Добавлены импорты `ImagesRepo` и `PromptsRepo` в `container.py`
  - Создание экземпляров репозиториев вынесено в `build_image_stack()`
  - `ImageCacheService` теперь получает конкретные реализации через конструктор
  - `container.py` является единственным местом создания конкретных реализаций

- **Переименование классов репозиториев БД Store → Repo**:
  - Переименованы классы репозиториев БД для единообразия: `ImagesStore` → `ImagesRepo`, `PromptsStore` → `PromptsRepo`, `ChatsStore` → `ChatsRepo`, `AdminsStore` → `AdminsRepo`, `ModelsStore` → `ModelsRepo`
  - Переименованы файлы: `*_store.py` → `*_repo.py` в `utils/`
  - Обновлены все импорты и использования классов в коде
  - Обновлены тесты и тестовые файлы
  - Обновлен `conftest.py` для использования новых имен классов
  - Четкое разделение: `*Repo` (репозитории БД) vs `*Storage` (файловые хранилища)

### Добавлено

- **Создание dataclass для конфигурации GigaChat**:
  - Создан файл `services/clients/gigachat_config.py` с dataclass `GigaChatConfig`
  - Инкапсулирует все параметры конфигурации GigaChat клиента (auth_url, api_url, authorization_key, scope, model, verify_ssl)
  - Добавлен метод `from_config()` для создания из глобального Config
  - Использует `frozen=True` для иммутабельности конфигурации

- **Создание dataclass для конфигурации Kandinsky**:
  - Создан файл `services/clients/kandinsky_config.py` с dataclass `KandinskyConfig`
  - Инкапсулирует все параметры конфигурации Kandinsky клиента (api_key, secret_key)
  - Добавлен метод `from_config()` для создания из глобального Config
  - Использует `frozen=True` для иммутабельности конфигурации

### Изменено

- **Рефакторинг конструктора GigaChatTextClient**:
  - Заменены все параметры конфигурации на один параметр `config: GigaChatConfig`
  - Удален fallback на глобальный `config` из конструктора
  - Удален импорт `from utils.config import config`
  - Конструктор теперь принимает только обязательный объект конфигурации
  - Устранена зависимость от глобального состояния

- **Рефакторинг конструктора KandinskyClient**:
  - Заменено чтение из глобального `config` на параметр `config: KandinskyConfig`
  - Удален импорт `from utils.config import config`
  - Конструктор теперь принимает только обязательный объект конфигурации
  - Исправлено использование config на уровне модуля для timeout константы
  - Устранена зависимость от глобального состояния

- **Обновление factory.py для использования config объектов**:
  - Функция `create_image_client` теперь принимает `kandinsky_config: KandinskyConfig`
  - Функция `create_text_client` теперь принимает `gigachat_config: GigaChatConfig`
  - Удален импорт глобального `config` из factory.py
  - Фабрики больше не зависят от глобального состояния

- **Обновление container.py для создания config объектов**:
  - `container.py` теперь единственное место, где импортируется глобальный `config`
  - Создание config объектов из глобального config через методы `from_config()`
  - Передача config объектов в factory функции
  - Соответствует принципу Composition Root

- **Обновление тестов для использования config объектов**:
  - Все тесты обновлены для использования GigaChatConfig и KandinskyConfig
  - Тесты больше не зависят от глобального config
  - Улучшена тестируемость клиентов

### Добавлено

- **Создание интерфейса ITaskQueue**:
  - Добавлен Protocol `ITaskQueue` в `services/protocols.py` для абстракции очереди задач
  - Определён метод `send_frog_manual_task()` с параметрами `chat_id`, `user_id`, `status_message_id`
  - Протокол абстрагирует детали реализации очереди задач от application-сервисов

- **Создание реализации CeleryTaskQueue**:
  - Создан класс `CeleryTaskQueue` в `services/infrastructure/celery/celery_task_queue.py`
  - Класс реализует `ITaskQueue` Protocol через Celery
  - Принимает `celery_app` в конструкторе с дефолтным значением
  - Использует `CeleryTaskNames` для имен задач
  - Инкапсулирует детали работы с Celery для отправки задач генерации жабы

- **Перемещение Celery в infrastructure слой**:
  - Перемещены все файлы из `services/celery/` в `services/infrastructure/celery/`
  - Обновлены все импорты в коде: `services.celery` → `services.infrastructure.celery`
  - Обновлены команды в `docker-compose.yml` для использования нового пути
  - Обновлены все тесты для использования нового пути импорта
  - Celery теперь правильно классифицирован как инфраструктурный сервис
  - Улучшена архитектурная структура: вся инфраструктура в одном месте

### Изменено

- **Устранение зависимости от конкретных реализаций в PromptService**:
  - Удалён импорт конкретного класса `PromptCache` из `services/application/prompt_service.py`
  - Упрощены типы в конструкторе `PromptService`: убран union с конкретным классом, оставлен только протокол `ICache[dict | str]`
  - Application слой теперь зависит только от абстракций (Protocol), а не от конкретных реализаций Infrastructure слоя
  - Улучшено соответствие принципу Dependency Inversion (DIP)
  - Упрощена замена реализаций кэша без изменения Application слоя

- **Рефакторинг WednesdayBot на Dependency Injection**:
  - Удалён импорт `build_bot_services` из `bot/wednesday_bot.py`
  - Изменена сигнатура конструктора `WednesdayBot.__init__()` для принятия `services: BotServices` через dependency injection
  - Удалён вызов `build_bot_services()` внутри конструктора
  - Обратная ссылка `services.bot_controller` устанавливается после присваивания сервисов
  - Устранена зависимость `WednesdayBot` → `container.py` на уровне импортов

- **Добавлена функция build_bot() в container.py**:
  - Добавлена функция `build_bot()` как единственная точка создания `WednesdayBot` в приложении
  - Функция использует ленивый импорт `WednesdayBot` для избежания циклических зависимостей
  - Функция принимает опциональный параметр `services` для возможности переиспользования существующих сервисов
  - Функция является Composition Root для `WednesdayBot`, обеспечивая правильный DI

- **Обновление main.py для использования build_bot()**:
  - Заменён импорт `WednesdayBot` на импорт `build_bot` из `services.container`
  - Заменено создание бота `WednesdayBot()` на вызов `build_bot()`
  - Все точки создания бота теперь используют единую функцию из composition root

- **Обновление services/celery/context.py для использования build_bot()**:
  - Удалён импорт `WednesdayBot` с уровня модуля
  - Добавлен ленивый импорт `build_bot` внутри функции `get_services_context()`
  - Заменено создание бота `WednesdayBot()` на вызов `build_bot()`
  - Добавлен `from __future__ import annotations` для корректной работы строковых аннотаций типов
  - Добавлен TYPE_CHECKING импорт для `WednesdayBot` в аннотациях типов
  - Использован ленивый импорт в методе `get_bot()` для проверки типа

- **Обновление тестов для использования нового API**:
  - Обновлена фикстура `wednesday_bot` для создания mock-сервисов и передачи их в конструктор
  - Удалён monkeypatch для `build_bot_services`, так как он больше не используется
  - Бот теперь создаётся с явной передачей сервисов через dependency injection
  - Тесты используют новый API с явными зависимостями

- **Рефакторинг FrogRequestService**:
  - Удалена прямая зависимость от `celery_app` и `CeleryTaskNames` в `FrogRequestService`
  - Добавлен конструктор, принимающий `task_queue: ITaskQueue` через dependency injection
  - Метод `request_manual_frog()` теперь использует `self.task_queue.send_frog_manual_task()`
  - Обновлён `container.py` для создания `CeleryTaskQueue` и передачи его в `FrogRequestService`
  - Обновлены `support_bot.py` и тесты для использования нового API
  - Устранена зависимость Application Layer → Infrastructure Layer

- **Устранение циклического импорта в Celery модуле**:
  - Удалён импорт `tasks` из `services/infrastructure/celery/__init__.py` для разрыва циклической зависимости
  - Добавлен комментарий о причинах отсутствия импорта `tasks` в `__init__.py`
  - Обновлён импорт `celery_app` в `tasks.py` на прямой импорт из `app.py` для надёжности
  - Обновлён импорт `celery_app` в `celery_task_queue.py` на прямой импорт из `app.py`
  - Tasks теперь регистрируются автоматически при импорте `tasks.py` в worker процессе
  - Устранён циклический импорт между `__init__.py` и `tasks.py`

- **Устранение прямого импорта WednesdayBot в tasks.py**:
  - Удалён импорт `WednesdayBot` на уровне модуля в `tasks.py` для устранения циклической зависимости
  - Добавлен условный импорт `WednesdayBot` через `TYPE_CHECKING` для типизации
  - Создана helper-функция `_get_wednesday_bot()` с ленивым импортом для проверки типа во время выполнения
  - Заменены все использования `isinstance(bot, WednesdayBot)` на вызов helper-функции
  - Устранена зависимость `tasks.py` → `WednesdayBot` на уровне импортов
  - Все задачи используют `get_services_context()` для получения бота через dependency injection

- **Обновление container.py для внедрения зависимостей**:
  - Перенесён импорт `FrogRequestService` внутрь функции `build_bot_services()` для избежания циклических зависимостей
  - Добавлен ленивый импорт `CeleryTaskQueue` внутри функции `build_bot_services()`
  - Создаётся экземпляр `CeleryTaskQueue` перед созданием `FrogRequestService`
  - `FrogRequestService` теперь получает `task_queue` через dependency injection в конструкторе
  - Устранена зависимость от глобального состояния при создании `FrogRequestService`

- **Рефакторинг PromptGenerationService: удаление зависимости от utils.config**:
  - Создан dataclass `PromptFallbackConfig` для инкапсуляции конфигурации fallback промптов
  - Добавлен метод `from_image_config()` для создания конфигурации из глобального `ImageConfig`
  - Изменен конструктор `PromptGenerationService` для принятия `fallback_config` через dependency injection
  - Метод `get_fallback_prompt()` преобразован из статического в метод экземпляра
  - Удалена зависимость от `utils.config.ImageConfig` в domain слое
  - Обновлен `container.py` для создания и передачи `PromptFallbackConfig` в `PromptGenerationService`

- **Удалено файловое хранилище промптов**:
  - Удалён избыточный слой файлового хранилища промптов (`PromptStorageService`, `IPromptStorage`)
  - Все промпты теперь хранятся только в базе данных PostgreSQL через `PromptsStore`
  - Удалён параметр `prompt_storage` из конструктора `PromptService`
  - Удалён параметр `prompt_storage` из конструктора `GigaChatTextClient`
  - Удалён параметр `prompt_storage` из функции `create_text_client()`
  - Обновлён `services/container.py` для удаления создания и передачи `PromptStorageService`
  - Удалён протокол `IPromptStorage` из `services/protocols.py`
  - Удалён файл `services/infrastructure/storage/prompt_storage.py`
  - Удалены тесты, использующие `PromptStorageService`
  - Упрощена архитектура за счёт удаления дублирования функциональности

- **Декомпозиция DispatchService.send_wednesday_frog**:
  - Разбит толстый метод `send_wednesday_frog` на приватные методы для улучшения читаемости и тестируемости
  - Выделены методы: `_init_result`, `_prepare_targets`, `_already_dispatched_for_all`, `_generate_image`, `_send_single_photo`, `_send_to_targets`, `_send_fallback_to_targets`, `_handle_generation_failure`, `_handle_unexpected_error`
  - Основной метод `send_wednesday_frog` теперь является тонким координирующим методом, вызывающим эти шаги
  - Каждый приватный метод инкапсулирует свою часть логики и может быть покрыт отдельными unit-тестами

- **Выделение форматирования сообщений из AdminDashboardService**:
  - Создан модуль `admin_dashboard_builders.py` с билдерами для форматирования сообщений
  - Добавлен `StatusMessageBuilder` для форматирования сообщения `/status`
  - Добавлен `ModelsListMessageBuilder` для форматирования сообщения `/list_models`
  - Созданы dataclass'ы `StatusData` и `ModelsListData` для передачи данных в билдеры
  - `AdminDashboardService` теперь фокусируется на сборе данных, а билдеры отвечают за форматирование
  - Упрощено unit-тестирование форматирования независимо от источников данных

- **Внедрён Dependency Injection для AdminDashboardService**:
  - Конструктор `AdminDashboardService` теперь принимает все зависимости извне: `image_client`, `text_client`, `models_store`
  - Удалены внутренние вызовы `create_image_client()`, `create_text_client()` и создание `ModelsStore()` внутри сервиса
  - Создана функция `build_admin_dashboard_service()` в `services/container.py` для сборки сервиса в composition root
  - `AdminDashboardService` добавлен в `BotServices` контейнер для передачи в handlers
  - Обновлены `bot/handlers_admin.py` и `bot/handlers_models.py` для использования `admin_dashboard_service` из `BotServices`
  - Все клиенты создаются один раз в `build_bot_services()` с единым `prompt_storage`, обеспечивая правильный DI и отсутствие дублирования
  - Сервис стал полностью управляемым через DI, упрощая тестирование и замену зависимостей

- **Введён протокол IRateLimiter и DI для FrogRateLimiterService**:
  - Добавлен новый протокол `IRateLimiter` в `services/protocols.py` с методами `is_allowed()` и `reset()`
  - Обновлён `FrogRateLimiterService` для принятия `IRateLimiter` через dependency injection вместо создания `RateLimiter` внутри
  - Обновлён `services/container.py` для создания экземпляров `RateLimiter` и передачи их в `FrogRateLimiterService`
  - Обновлены `bot/support_bot.py` и тесты для использования нового API с DI
  - Application-сервис теперь зависит от интерфейса, что упрощает тестирование и замену реализации

- **Удалён дубликат конфигурации Celery**:

- **Унифицировано файловое хранилище промптов**:
  - Удалён синхронный класс `PromptStorage` из `services/prompt_generator.py`, оставлена только асинхронная реализация `PromptStorageService`
  - Удалён устаревший модуль `services/prompt_generator.py` после завершения миграции на `PromptStorageService`
  - `GigaChatTextClient` теперь принимает `IPromptStorage` через dependency injection вместо создания хранилища внутри себя
  - Фабрика `create_text_client()` в `services/clients/factory.py` принимает опциональный параметр `prompt_storage` для передачи в клиент
  - В `services/container.py` создаётся единый экземпляр `PromptStorageService` и передаётся в `create_text_client()` и `PromptService`
  - Обновлены тесты для использования асинхронного `PromptStorageService` вместо синхронного `PromptStorage`
  - Обновлён пример в `docs/TESTING_GUIDE.md` для использования `PromptStorageService` вместо устаревшего `PromptStorage`

- **Консолидирован circuit breaker**:
  - Удалён legacy-класс `CircuitBreaker` из `services/infrastructure/rate_limiting/rate_limiter.py`
  - Оставлена только реализация `CircuitBreakerService` в отдельном модуле `circuit_breaker.py`
  - Обновлён `__init__.py` для экспорта только `CircuitBreakerService` и `RateLimiter`
  - Обновлены тесты для использования `CircuitBreakerService` вместо legacy-класса `CircuitBreaker`

- **Удалён дубликат конфигурации Celery**:
  - Удалён устаревший модуль `services/celery_app.py` (дубликат `services/celery/app.py`)
  - Обновлены команды в `docker-compose.yml` и `docs/DEPLOYMENT.md` для использования `services.celery` вместо `services.celery_app`
  - Обновлена структура проекта в `README.md` для отражения новой организации Celery модулей

- **Реорганизована структура Celery модулей**:
  - Переименован `services/celery_tasks.py` → `services/celery/context.py` для улучшения ясности структуры
  - Модуль `context.py` содержит инфраструктуру и управление жизненным циклом сервисов (инициализация, shutdown)
  - Модуль `tasks.py` содержит бизнес-логику Celery задач
  - Обновлены все импорты в тестах и документации для использования нового пути `services.celery.context`

- **Удалён legacy планировщик TaskScheduler**:
  - Удалён модуль `services/scheduler.py` с классом `TaskScheduler` (legacy планировщик на основе asyncio)
  - Удалён неиспользуемый модуль `services/application/scheduler_service.py`
  - Удалён протокол `IScheduler` из `services/protocols.py` (больше не используется)
  - Удалено поле `scheduler` из `BotServices` и логика создания TaskScheduler в `container.py`
  - Удалён метод `setup_scheduler()` и все использования scheduler из `WednesdayBot`
  - Удалён флаг `use_old_scheduler` из `utils/config.py` и переменная окружения `USE_OLD_SCHEDULER` из `env_example.txt`
  - Удалены тесты для TaskScheduler (`tests/test_services/test_scheduler.py`)
  - Обновлена документация: удалены упоминания TaskScheduler из `docs/ARCHITECTURE.md`
  - Теперь используется только Celery Beat для планирования задач (production-ready решение)

- **Удалён неиспользуемый атрибут next_run_provider из handlers**:
  - Удалён параметр `next_run_provider` из конструкторов `UserHandlers`, `AdminHandlers` и `ModelHandlers`
  - Удалена логика отображения времени следующей отправки из команд `/start`, `/help` и `/status`
  - Удалён параметр `next_run_provider` из `AdminDashboardService.build_status_message()`
  - Упрощены сообщения пользователям: убрана информация о следующей отправке (недоступна после удаления TaskScheduler)
  - Обновлены все тесты: убраны параметры `next_run_provider` из вызовов handlers
  - Удалены неиспользуемые импорты `Callable` и `datetime` из handlers

- **Исправлено форматирование строк в логировании**:
  - Заменено старое форматирование (`%s`, `%r`, `%d`) на f-strings во всех logger вызовах в `services/`
  - Исправлено в `services/application/dispatch_service.py` (7 мест)
  - Исправлено в `services/application/image_service.py` (2 места)
  - Исправлено в `services/infrastructure/cache/image_cache.py` (1 место)
  - Исправлено в `services/clients/factory.py` (2 места)
  - Loguru не поддерживает старое форматирование, теперь используется f-strings для совместимости

- **Уточнены импорты и структура административных хэндлеров**:
  - В `bot/handlers_admin.py` импорт `LOGS_DIR` перенесён на уровень модуля для соблюдения единого стиля группировки импортов
  - Структура импортов в ключевых модулях (`bot/wednesday_bot.py`, `services/application/image_service.py`) проверена на соответствие порядку stdlib → third‑party → internal
  - В административных обработчиках сохранена зависимость только от `BotServices` и утилитного слоя без прямых импортов инфраструктуры

- **Формализован shutdown ML-клиентов в общем месте**:
  - В `services/celery_tasks.py` функция `shutdown_services()` теперь закрывает `ImageClientContainer` и `TextClientContainer` через `aclose()` для гарантированного закрытия HTTP-сессий
  - В `bot/wednesday_bot.py` добавлен метод `aclose()` для закрытия контейнеров ML-клиентов при остановке standalone-бота
  - Метод `WednesdayBot.stop()` вызывает `aclose()` для освобождения ресурсов HTTP-клиентов перед остановкой приложения
  - Документирован контракт shutdown в `docs/MONITORING.md`: при остановке сервиса необходимо вызывать `aclose()` у контейнеров ML-клиентов для корректного закрытия всех HTTP-сессий

- **Выделен DispatchService для cron‑логики send_wednesday_frog**:
  - Создан application‑сервис `DispatchService` в `services/application/dispatch_service.py` для координации рассылки жабы по расписанию
  - В `services/container.py` сервис собирается через DI и прокидывается в `BotServices.dispatch_service`
  - Метод `WednesdayBot.send_wednesday_frog` стал тонким glue‑кодом: вычисляет `slot_time`/`slot_date` и делегирует основную логику в `DispatchService`
  - Логика работы с `dispatch_registry`, `usage`, `metrics`, `chats` и `ImageService` инкапсулирована в application‑слое

- **Вынесена сложная логика админских команд в AdminDashboardService**:
  - Создан application‑сервис `AdminDashboardService` в `services/application/admin_dashboard_service.py` для агрегации метрик, лимитов, чатов и статусов API
  - Команда `/status` в `bot/handlers_admin.py` использует `AdminDashboardService.build_status_message()` вместо ручного сбора и форматирования данных в хэндлере
  - Команда `/list_models` в `bot/handlers_models.py` использует `AdminDashboardService.build_models_list_message()` для вывода списка моделей Kandinsky и GigaChat
  - Повторяющаяся логика работы с `ModelsStore`, ML‑клиентами и форматированием перенесена из хэндлеров в application‑слой

- **Усилена типизация кэшей и протокола ICache**:
  - Протокол `ICache` в `services/protocols.py` стал generic-интерфейсом `ICache[T]` с точным типом значения
  - `ImageCacheService` в `services/infrastructure/cache/image_cache.py` реализует `ICache[tuple[bytes, str]]` с уточнёнными сигнатурами `get` и `set`
  - `PromptCache` в `services/infrastructure/cache/prompt_cache.py` реализует `ICache[dict | str]` поверх Redis/in-memory backend
  - `ImageService` и `PromptService` в application-слое используют `ICache` с конкретными параметрами типов для кэшей изображений и промптов

- **Минимизирован доступ к приватному файловому хранилищу изображений**:
  - В `services/application/image_service.py` добавлен публичный метод `get_random_saved_image()` для получения случайного сохранённого изображения через application-слой
  - Методы fallback в `bot/wednesday_bot.py`, `bot/handlers_admin.py` и `services/celery/tasks.py` используют `ImageService` вместо прямого доступа к приватному полю `_storage`

- **Введён протокол IScheduler и абстрагирован планировщик через него**:
  - Добавлен протокол `IScheduler` в `services/protocols.py` с методами управления задачами и получения состояния без утечки внутренних полей конкретной реализации
  - `SchedulerService` в `services/application/scheduler_service.py` теперь зависит от `IScheduler`, а не от конкретного `TaskScheduler`
  - Поле `scheduler` в `BotServices` и контейнере `build_bot_services()` типизировано через `IScheduler | None`, что позволяет подменять реализацию планировщика
  - Валидация конфигурации слотов и выбор временных окон в `bot/wednesday_bot.py` теперь основаны на `AppSettings`, а не на прямом доступе к полям планировщика

- **Разделены протоколы файловых хранилищ для изображений и промптов**:
  - Протокол `IStorage` переименован в `IImageStorage` в `services/protocols.py` и используется только для байтового хранилища изображений
  - Добавлен протокол `IPromptStorage` в `services/protocols.py` с методами `save()` и `load_all()` для работы с файловым хранилищем промптов
  - `PromptService` в `services/application/prompt_service.py` теперь зависит от `ICache` и `IPromptStorage`, сохраняя текущие реализации (`PromptCache`, `PromptStorageService`) через DI

- **Введён протокол ICircuitBreaker и переведён ImageService на использование протокола**:
  - Добавлен протокол `ICircuitBreaker` в `services/protocols.py` с методами `is_open()`, `record_success()`, `record_failure()`
  - Параметр `circuit_breaker` в `services/application/image_service.py` типизирован через `ICircuitBreaker | None`
  - В `services/container.py` инфраструктурный `CircuitBreakerService` передаётся в `ImageService` как значение типа `ICircuitBreaker`

- **ImageService и кэш/хранилище изображений переведены на протоколы ICache/IImageStorage/IMetrics**:
  - Параметры `image_cache`, `image_storage`, `metrics` в `services/application/image_service.py` типизированы через `ICache`, `IImageStorage`, `IMetrics`
  - `ImageCacheService` реализует протокол `ICache` (методы `get`, `set`, `delete`) поверх существующих операций `get_by_prompt` и `save`
  - Логика работы с кэшем в `ImageService` использует протокольный интерфейс `ICache` и кодирует значение как `(image_data, caption)`
  - `ImageStorageService` и `MetricsRecorder` продолжают удовлетворять протоколам `IImageStorage` и `IMetrics` без изменений публичного API

- **Централизованы настройки rate limit для команды /frog**:
  - Удалены константы `FROG_RATE_LIMIT_MINUTES`, `FROG_RATE_LIMIT_WINDOW_SECONDS`, `FROG_RATE_LIMIT_MAX_REQUESTS` из `bot/handlers_user.py`
  - Настройки лимитов теперь читаются из `AppSettings` через DI (`self.services.settings`)
  - Унифицирована работа с настройками rate limit через единую точку конфигурации

- **Создан `FrogRateLimiterService` для проверки rate limit команды /frog**:
  - Создан application-сервис `services/application/frog_limit_service.py` для инкапсуляции логики rate limiting
  - Сервис проверяет глобальный и per-user лимиты через инфраструктурный `RateLimiter`
  - Администраторы пропускают per-user лимит, но подчиняются глобальному лимиту
  - Метод `check_and_consume()` возвращает понятный результат (bool, сообщение) для хэндлера
  - Добавлен `frog_rate_limiter` в `BotServices` и контейнер
  - Обновлён `UserHandlers.frog_command` для использования нового сервиса вместо прямого создания `RateLimiter`

- **Создан `FrogRequestService` для постановки задач в очередь Celery**:
  - Создан перечисление `CeleryTaskNames` в `services/celery/task_names.py` для централизации имён задач
  - Создан application-сервис `services/application/frog_requests.py` для инкапсуляции логики постановки задач в Celery
  - Сервис скрывает детали работы с `celery_app` от handlers
  - Добавлен `frog_request_service` в `BotServices` и контейнер
  - Обновлён `UserHandlers.frog_command` для использования нового сервиса вместо прямого вызова `celery_app.send_task`
  - Убраны прямые импорты `celery_app` из `UserHandlers`

- **Рефакторинг `services/celery_tasks.py`**:
  - Упрощён класс `CeleryServices` - удалены глобальные переменные `_bot`, `_generator`, `_initialized`, `_init_lock`
  - Создана функция `get_services_context()` для получения сервисов через dependency injection
  - Обновлены все задачи для использования контекста сервисов вместо глобального состояния
  - Класс `CeleryServices` оставлен для обратной совместимости (deprecated)
  - Улучшена типизация всех методов

- **Создан `services/celery/app.py`**:
  - Вынесена конфигурация Celery из `services/celery_app.py` в `services/celery/app.py`
  - Обновлены все импорты в проекте (bot/, services/, tests/)
  - Обновлён `services/celery/__init__.py` для экспорта `celery_app`

- **Создан `services/celery/tasks.py`**:
  - Перемещены все Celery задачи из `services/celery_tasks.py` в `services/celery/tasks.py`
  - Перемещены вспомогательные функции `is_retryable_error()` и `log_celery_task()`
  - Обновлён `services/celery_tasks.py` - теперь содержит только функции инициализации сервисов
  - Обновлён `services/celery/__init__.py` для импорта задач

- **Улучшена типизация `services/scheduler.py`**:
  - Создан `SchedulerConfigDict` TypedDict для конфигурации планировщика
  - Убрана прямая зависимость от `utils.config.SchedulerConfig`
  - Конфигурация передаётся через параметры конструктора
  - Добавлены значения по умолчанию для обратной совместимости
  - Обновлён `bot/wednesday_bot.py` для передачи конфигурации

- **Создан `services/application/scheduler_service.py`**:
  - Создан класс `SchedulerService(BaseService)` для оркестрации планирования
  - Использует протокол `IScheduler` как абстракцию над инфраструктурным планировщиком (по умолчанию `TaskScheduler`)
  - Реализованы методы для планирования задач и управления жизненным циклом
  - Разделение на domain/infrastructure/application соблюдено

- **Обновлена документация сервисов под новые протоколы**:
  - В `services/application/prompt_service.py` docstring-и отражают использование протоколов `ICache[dict | str]` и `IPromptStorage` вместо жёсткой привязки к реализациям
  - В `services/application/scheduler_service.py` уточнено, что сервис работает через протокол `IScheduler`, а конкретный планировщик скрыт за интерфейсом
  - В `services/container.py` обновлён модульный docstring под роль composition root и актуальный граф зависимостей
  - В `docs/ARCHITECTURE.md` добавлен раздел о протокольном слое (`ICircuitBreaker`, `IScheduler`, `ICache[T]`, `IImageStorage`, `IPromptStorage`) и обновлено описание `ImageService` под новые интерфейсы

### Изменено

- **Создан `services/domain/image_generation.py`**:
  - Создан класс `ImageGenerationService(BaseService)` для чистой генерации изображений
  - Вынесена логика генерации из `ImageGenerator` без зависимостей от инфраструктуры
  - Реализован метод `generate()` для генерации через `ITextToImageClient`
  - Добавлена обработка ошибок через `ImageGenerationError`

- **Создан `services/domain/prompt_generation.py`**:
  - Создан класс `PromptGenerationService(BaseService)` для чистой генерации промптов
  - Вынесена логика генерации промптов из `ImageGenerator` без зависимостей от инфраструктуры
  - Реализован метод `generate()` для генерации через `ITextToTextClient`
  - Добавлен статический fallback через `get_fallback_prompt()`
  - Добавлена обработка ошибок через `PromptGenerationError`

- **Создан `services/infrastructure/rate_limiting/circuit_breaker.py`**:
  - Создан класс `CircuitBreakerService(RedisBackendService)` для работы с circuit breaker
  - Вынесена логика circuit breaker из `rate_limiter.py` в отдельный сервис
  - Реализованы методы `is_open()`, `record_success()`, `record_failure()` с использованием Redis
  - Добавлена обработка ошибок через `CircuitBreakerOpen`
  - Использует `RedisBackendService` для автоматического fallback на in-memory
  - Заменено использование старого CircuitBreaker на CircuitBreakerService в image_generator.py

- **Перемещён `services/rate_limiter.py` → `services/infrastructure/rate_limiting/rate_limiter.py`**:
  - Файл перемещён в директорию `infrastructure/rate_limiting/` согласно новой архитектуре
  - Обновлены все импорты в проекте (bot/, services/, tests/)
  - Обновлён `services/infrastructure/rate_limiting/__init__.py` для экспорта

- **Создан `services/application/prompt_service.py`**:
  - Создан класс `PromptService(BaseService)` для координации генерации промптов
  - Координирует работу PromptGenerationService, PromptCache и PromptStorageService
  - Реализован метод `generate()` с полной координацией всех шагов
  - Добавлено логирование всех этапов генерации

- **Создан `services/infrastructure/metrics/metrics_recorder.py`**:
  - Создан класс `MetricsRecorder(BaseService, IMetrics)` для записи метрик
  - Реализует протокол IMetrics, оборачивая utils.metrics.Metrics
  - Добавлено логирование всех записей метрик

- **Создан `services/application/image_service.py`**:
  - Создан класс `ImageService(BaseService)` для координации генерации изображений
  - Координирует работу всех сервисов: ImageGenerationService, ImageCacheService,
    ImageStorageService, PromptService, CircuitBreakerService, MetricsRecorder

- **Централизовано использование `Config` в `ImageService`**:
  - Убрано прямое чтение глобального `config` из `services/application/image_service.py`
  - `max_retries` и набор подписей для изображений теперь передаются через DI из `services/container.py`
  - Контейнер читает значения из `utils.config.ImageConfig` и `config` и передаёт их в конструктор `ImageService`

- **Обновлены тесты и документация под финальную архитектуру `ImageService` и `BotServices`**:
  - Тест `tests/test_bot/test_wednesday_bot.py` переписан на использование DI‑контейнера `build_bot_services()` и `ImageService` вместо устаревшего `ImageGenerator`
  - В `docs/ARCHITECTURE.md` разделы про генерацию изображений и DI обновлены: `ImageService` описан как основной application‑сервис, зафиксирован финальный контракт `BotServices`
  - Уточнён `PROJECT_SUMMARY.md` и справочная документация по DI, чтобы отражать новую структуру контейнера и потоки зависимостей

### Добавлено

- **Создан `services/container.py`**:
  - Введён модуль сборки зависимостей для backend‑части бота
  - Реализована функция `build_image_stack()` для централизованной сборки стека `ImageService`

- **Расширен DI‑контейнер `BotServices` и контейнер сервисов**:
  - В `BotServices` добавлено поле `image_service` для работы с `ImageService` через DI
  - В `services/container.py` реализована функция `build_bot_services()` для сборки контейнера `BotServices`

- **Упрощён и зафиксирован контракт `BotServices`**:
  - Удалено неиспользуемое поле `rate_limiter` из `services/bot_services.py` и контейнера
  - Оставлены только те зависимости, к которым реально обращаются хэндлеры и `WednesdayBot`
  - Тип поля `scheduler` выражен как `TaskScheduler | None` для явного обозначения опциональности

- **Переведён `WednesdayBot` на DI‑контейнер**:
  - Вся сборка сервисов перенесена в `build_bot_services()`, `WednesdayBot` получает только готовый `BotServices`
  - Использование сервисов внутри `WednesdayBot` унифицировано через `self.services.*` без прокси‑полей
  - Fallback‑отправка изображений переведена на использование файлового хранилища `ImageStorageService`

- **Удалён legacy‑генератор `ImageGenerator`**:
  - Логика генерации и fallback‑обработки окончательно переведена на `ImageService` и `ImageStorageService`
  - Admin/Model‑хэндлеры используют клиентские контейнеры (`create_image_client`, `create_text_client`) вместо `ImageGenerator`
  - Celery‑таски и smoke/typing‑тесты обновлены для работы без `services/image_generator.py`
  - Реализован метод `generate_frog_image()` с полной координацией всех шагов
  - Добавлена обработка всех исключений и graceful degradation

- **Обновлён `services/image_generator.py` для использования новых сервисов**:
  - ImageGenerator теперь является тонкой обёрткой над ImageService
  - Метод `generate_frog_image()` использует новый ImageService внутри
  - Сохранён публичный интерфейс для обратной совместимости
  - Добавлен deprecation warning в docstring (будет удалён в спринте 5)
  - Создание всех сервисов вынесено в метод `_create_image_service()`

### Изменено

- **Рефакторинг `services/prompt_cache.py`**:
  - Класс `PromptCache` теперь наследуется от `RedisBackendService`
  - Удалена дублированная логика fallback, используется `_execute_with_fallback` из базового класса
  - Все методы обновлены для использования базового класса
  - Сохранена обратная совместимость интерфейса

- **Рефакторинг `services/rate_limiter.py`**:
  - Класс `RateLimiter` теперь наследуется от `RedisBackendService`
  - Удалена дублированная логика fallback, используется `_execute_with_fallback` из базового класса
  - Все методы обновлены для использования базового класса
  - Сохранена обратная совместимость интерфейса

- **Рефакторинг `services/user_state_store.py`**:
  - Класс `UserStateStore` теперь наследуется от `RedisBackendService`
  - Удалена дублированная логика fallback, используется `_execute_with_fallback` из базового класса
  - Все методы обновлены для использования базового класса
  - Сохранена обратная совместимость интерфейса

- **Создан `services/infrastructure/storage/image_storage.py`**:
  - Создан класс `ImageStorageService(BaseService)` для работы с файловым хранилищем изображений
  - Вынесена логика сохранения изображений из `ImageGenerator.save_image_locally()`
  - Реализованы асинхронные методы `save()` и `get_random()` с использованием `asyncio.to_thread()`
  - Добавлена обработка ошибок через `StorageError`

- **Создан `services/infrastructure/storage/prompt_storage.py`**:
  - Создан класс `PromptStorageService(BaseService)` для работы с файловым хранилищем промптов
  - Вынесена логика сохранения промптов из `PromptGenerator.save_prompt()`
  - Реализованы асинхронные методы `save()` и `load_all()` с использованием `asyncio.to_thread()`
  - Добавлена обработка ошибок через `StorageError`

- **Создан `services/infrastructure/cache/image_cache.py`**:
  - Создан класс `ImageCacheService(BaseService)` для кэширования изображений по промптам
  - Вынесена логика кэширования изображений из `ImageGenerator`
  - Реализованы методы `get_by_prompt()`, `get_by_hash()` и `save()` для работы с кэшем
  - Использует `ImagesStore` и `PromptsStore` для работы с базой данных
  - Добавлена обработка ошибок через `CacheError`

- **Перемещён `services/prompt_cache.py` → `services/infrastructure/cache/prompt_cache.py`**:
  - Файл перемещён в директорию `infrastructure/cache/` согласно новой архитектуре
  - Обновлены все импорты в проекте
  - Обновлён `services/infrastructure/cache/__init__.py` для экспорта

- **Перемещён и переименован `services/user_state_store.py` → `services/infrastructure/cache/user_state_cache.py`**:
  - Файл перемещён в директорию `infrastructure/cache/` согласно новой архитектуре
  - Класс `UserStateStore` переименован в `UserStateCache`
  - Обновлены все импорты в проекте
  - Обновлён `services/infrastructure/cache/__init__.py` для экспорта

### Добавлено

- **Структура директорий для новой архитектуры services/**:
  - Создана директория `services/base/` для базовых классов и исключений
  - Создана директория `services/domain/` для доменной логики
  - Создана директория `services/application/` для application services (координаторов)
  - Создана директория `services/infrastructure/` с поддиректориями для cache, storage, rate_limiting, metrics
  - Создана директория `services/celery/` для Celery задач и сервисов
  - Все директории содержат базовые `__init__.py` файлы с экспортами

- **Иерархия кастомных исключений в `services/base/exceptions.py`**:
  - Создан базовый класс `ServiceException` для всех ошибок сервисов
  - Добавлено исключение `ImageGenerationError` для ошибок генерации изображений
  - Добавлено исключение `CacheError` для ошибок работы с кэшем
  - Добавлено исключение `RateLimitExceeded` для превышения лимита запросов
  - Добавлено исключение `CircuitBreakerOpen` для открытого circuit breaker
  - Добавлено исключение `PromptGenerationError` для ошибок генерации промптов
  - Добавлено исключение `StorageError` для ошибок работы с хранилищем
  - Все исключения имеют docstrings и наследуются от `ServiceException`

- **Базовый класс `BaseService` в `services/base/base_service.py`**:
  - Создан базовый класс `BaseService` для всех сервисов
  - Добавлено свойство `self.logger` через `get_logger(self.__class__.__name__)`
  - Добавлен метод `log_event()` для унифицированного логирования событий
  - Класс полностью типизирован с использованием `from __future__ import annotations`

- **Базовый класс `RedisBackendService` в `services/base/redis_backend_service.py`**:
  - Создан базовый класс `RedisBackendService(BaseService)` для Redis-сервисов
  - Реализован `__init__(redis_client, prefix="")` с fallback на `get_redis()`
  - Реализовано приватное поле `_fallback: _InMemoryRedis` для in-memory fallback
  - Реализован метод `_key(key: str) -> str` для работы с префиксами ключей
  - Реализован метод `_execute_with_fallback()` с типизацией через `TypeVar` и `Callable`
  - Добавлено логирование fallback-переходов через self.logger
  - Класс полностью типизирован с использованием `from __future__ import annotations`

- **Протоколы зависимостей в `services/protocols.py`**:
  - Создан протокол `IMetrics` с методами для работы с метриками:
    - `increment_generation_success()` — успешные генерации
    - `increment_generation_failed()` — неудачные генерации
    - `increment_cache_hit()` — попадания в кэш
    - `increment_dispatch_success()` — успешные отправки
    - `increment_dispatch_failed()` — неудачные отправки
    - `record_circuit_breaker_trip()` — срабатывания circuit breaker
  - Создан протокол `IStorage` для файлового хранилища с методами `save()` и `get_random()`
  - Создан протокол `ICache` для кэширования с методами `get()`, `set()`, `delete()`
  - Все протоколы используют `@runtime_checkable` для проверки через `isinstance`
  - Протоколы полностью типизированы с использованием `from __future__ import annotations`

### Изменено

- **Добавлен `from __future__ import annotations` во все файлы services/**:
  - Добавлен импорт в `services/prompt_generator.py`
  - Добавлен импорт в `services/image_generator.py`
  - Добавлен импорт в `services/celery_app.py`
  - Добавлен импорт в `services/celery_tasks.py`
  - Добавлен импорт в `services/scheduler.py`
  - Все файлы services/ теперь используют отложенную оценку аннотаций типов

- **Улучшена типизация в `services/scheduler.py`**:
  - Заменён `dict[str, Any]` на типизированный `dict[str, TaskValue]`
  - Создан `TypedDict` `DailyTaskConfig` для конфигурации ежедневных задач
  - Создан `TypedDict` `IntervalTaskConfig` для конфигурации интервальных задач
  - Создан тип `TaskValue` как Union всех возможных типов значений задач
  - Убрано использование `Any` в типах задач

- **Улучшена типизация в `services/celery_tasks.py`**:
  - Улучшена типизация декоратора `log_celery_task` с использованием `TypeVar` для возвращаемого значения
  - Заменён `Any` на `TypeVar R` для возвращаемого значения декоратора
  - Все методы класса `CeleryServices` уже имеют полную типизацию
  - Декоратор теперь правильно типизирован с сохранением сигнатуры обёрнутой функции

---

## [6.14.1] 2025-12-17 — Удаление неисползуемого модуля и обновление тестов

### Изменено

- **Удаление неиспользуемого модуля `bot/handlers.py`**:
  - Удален пустой файл `bot/handlers.py`: файл содержал только docstring после переноса всех команд в специализированные хендлеры
  - Обновлены тесты `tests/test_bot/test_handlers.py`: удалены неиспользуемые импорты и вызовы `importlib.reload` для пустого модуля `bot.handlers`

---

## [6.14.0] 2025-12-17 — Унификация путей, переход на Tenacity и упрощение инфраструктурных утилит

### Изменено

- **Рефакторинг управления путями (paths.py)**:
  - Упрощена структура модуля `utils/paths.py`: удалены дублирующие константы `*_CONTAINER_PATH` и функции `resolve_*()`
  - Добавлена базовая константа `DATA_DIR = Path("data")` для единообразного определения путей к данным
  - Обновлены константы на использование `pathlib.Path` объектов вместо строк
  - Переименована константа `FROG_IMAGES_DIR` в `FROGS_DIR` для краткости
  - Все пути теперь определены относительно корня проекта и автоматически разрешаются через `pathlib.Path`
  - Обновлен `services/image_generator.py`: заменены импорты и использование старых констант на `FROGS_DIR`
  - Упрощено логирование в `image_generator.py`: убраны упоминания контейнерных путей
  - Обновлены типы параметров `folder` в методах сохранения и получения изображений на `Path | str`
  - Обновлен `utils/images_store.py`: заменены импорты `FROG_IMAGES_CONTAINER_PATH` и `resolve_frog_images_dir` на `FROGS_DIR`
  - Упрощен метод `_container_path_for_hash` в `images_store.py`: теперь возвращает относительный путь через `str(FROGS_DIR / ...)`
  - Упрощено логирование в `images_store.py`: убраны упоминания контейнерных путей
  - Обновлен `utils/logger.py`: заменены импорты `LOGS_CONTAINER_PATH` и `resolve_logs_dir` на `LOGS_DIR`
  - Упрощено логирование в `logger.py`: заменено упоминание `LOGS_CONTAINER_PATH` на `LOGS_DIR` в сообщении о настройке логирования
  - Обновлен `services/prompt_generator.py`: заменены импорты `PROMPTS_CONTAINER_PATH` и `resolve_prompts_dir` на `PROMPTS_DIR`
  - Упрощено логирование в `prompt_generator.py`: заменено упоминание `PROMPTS_CONTAINER_PATH` на `PROMPTS_DIR / filename` в сообщении о сохранении промпта
  - Обновлен `bot/handlers_admin.py`: заменены импорты `LOGS_CONTAINER_PATH` и `LOGS_DIR` на только `LOGS_DIR`
  - Упрощено использование путей в `handlers_admin.py`: заменено `Path(LOGS_DIR)` на прямое использование `LOGS_DIR`
  - Упрощено логирование в `handlers_admin.py`: убраны упоминания контейнерных путей из сообщений о логах
  - Обновлен `tests/test_utils/test_paths.py`: переписаны тесты для проверки новых констант `DATA_DIR`, `FROGS_DIR`, `LOGS_DIR`, `PROMPTS_DIR` вместо старых `*_CONTAINER_PATH` констант
  - Обновлен `tests/test_utils/test_images_store.py`: заменен патчинг функции `resolve_frog_images_dir` на патчинг константы `FROGS_DIR` в обоих тестах
  - Обновлен `tests/test_utils/test_logger_secrets.py`: заменен патчинг функции `resolve_logs_dir` на патчинг константы `LOGS_DIR` в тесте `test_json_logs_do_not_contain_gigachat_key`
  - Удалены временные deprecated алиасы из `utils/paths.py`: `FROG_IMAGES_DIR`, `FROG_IMAGES_CONTAINER_PATH`, `LOGS_CONTAINER_PATH`, `PROMPTS_CONTAINER_PATH` и функции `resolve_*()`
  - Переименован метод `_container_path_for_hash` в `_relative_path_for_hash` в `utils/images_store.py` для лучшей семантики

- **Унификация retry-механизма с использованием Tenacity**:
  - Добавлены импорты `httpx`, `telegram.error` и дополнительные компоненты Tenacity в `utils/retry.py`
  - Добавлен класс `WaitTelegramLinear` для линейного backoff и обработки 429 ошибок
  - Добавлена функция-предикат `_should_retry_telegram_error()` для определения необходимости retry
  - Добавлена функция `retry_on_connect_error()` на базе Tenacity для замены реализации из `telegram_retry.py`
  - Добавлен декоратор `retry_telegram()` как аналог `retry_on_telegram_error()` из `telegram_retry.py`
  - Обновлены импорты в `bot/base_handlers.py`: заменен `utils.telegram_retry` на `utils.retry`
  - Обновлены импорты в `bot/wednesday_bot.py`: заменен `utils.telegram_retry` на `utils.retry`
  - Заменен декоратор `retry_on_telegram_error` на `retry_telegram` в `BaseHandlers._safe_reply_text`
  - Удален файл `utils/telegram_retry.py` после переноса функциональности в `utils/retry.py`
  - Обновлен комментарий в `base_handlers.py` с упоминанием нового пути к helper'у

- **Реорганизация тестового кода**:
  - Перемещен файл `utils/config_test.py` в `tests/utils/config_test.py` для правильной организации тестового кода
  - Обновлен импорт в `tests/common/celery_app_test.py` на использование нового пути `tests.utils.config_test`

---

## [6.13.0] 2025-12-17 — Завершение DI, BaseHandlers вместо CommandHandlers и масштабируемый rate limiting

### Изменено

- **Обновление документации архитектуры для SupportBot**:
  - Обновлен раздел `SupportBot` в `ARCHITECTURE.md` с информацией о наследовании от `BaseHandlers`
  - Добавлена информация об использовании `AppSettings` для доступа к настройкам через DI
  - Добавлена информация о минимальном `BotServices` для `SupportBot`
  - Добавлена информация об унифицированном retry helper и классификации исключений в `SupportBot`
  - Обновлен раздел `Handler Architecture` с упоминанием `SupportBot` как наследника `BaseHandlers`
  - Обновлен раздел `Dependency Injection` с информацией о минимальном `BotServices` для `SupportBot`
  - Обновлен раздел `Retry Policy` с информацией об использовании retry helper в `SupportBot`
  - Обновлен раздел `Классификация исключений` с информацией о применении в `SupportBot`

- **Использование BaseHandlers для переиспользования общих методов в SupportBot**:
  - Создан минимальный `BotServices` в `SupportBot.__init__` с полями `settings` и `rate_limiter` для использования `BaseHandlers`
  - Изменено объявление класса `SupportBot` для наследования от `BaseHandlers`
  - Обновлен порядок инициализации: сначала создаются все компоненты, затем вызывается `super().__init__(services)`
  - Удалено дублирующее поле `self.logger` (используется из `BaseHandlers`)
  - Удалено дублирующее поле `self.admins` (используется `self.admins_store` из `BaseHandlers`)
  - Заменены все обращения к `self.admins` на `self.admins_store` в методах `_is_admin`, `start` и `stop`
  - Заменены все прямые вызовы `retry_on_connect_error` на использование `self._retry_on_connect_error` из `BaseHandlers` для консистентности
  - Удален импорт `retry_on_connect_error` из `utils.telegram_retry` (используется метод из `BaseHandlers`)
  - Обновлен docstring метода `_is_admin`: указано использование `self.admins_store` из `BaseHandlers`
  - Добавлены комментарии в местах использования методов из `BaseHandlers` для ясности

- **Унификация retry-политики в SupportBot**:
  - Добавлен импорт `retry_on_connect_error` из `utils.telegram_retry` в `SupportBot`
  - Обернуты все вызовы отправки сообщений в `retry_on_connect_error` для обеспечения консистентности с `WednesdayBot`
  - Обновлен метод `maintenance_message`: обернут `reply_text` в `retry_on_connect_error` с параметрами `max_retries=3, delay=2.0, handle_rate_limit=True`
  - Обновлен метод `log_command`: обернуты все вызовы `reply_text` и `_send_log_file` в `retry_on_connect_error`
  - Обновлен метод `_send_log_file`: обернут `send_document` в `retry_on_connect_error`
  - Обновлен метод `start_main_command`: обернут `reply_text` в `retry_on_connect_error`
  - Обновлен метод `help_command`: обернут `reply_text` в `retry_on_connect_error`
  - Обновлен метод `start`: обернут `send_message` в `retry_on_connect_error` для уведомлений администраторам
  - Обновлен метод `stop`: обернут `send_message` в `retry_on_connect_error` для уведомлений администраторам

- **Классификация исключений в SupportBot**:
  - Добавлен импорт `TelegramError` из `telegram.error` для классификации исключений
  - Заменены все `except Exception:` на конкретные типы исключений для улучшения отладки и обработки ошибок
  - Infrastructure ошибки (retry + мягкая деградация): `except (TelegramError, NetworkError, TimedOut):` для сетевых/Telegram ошибок в методах отправки сообщений
  - Programming/Business ошибки: `except (ValueError, TypeError, AttributeError):` для логических ошибок (преобразование типов, доступ к атрибутам)
  - Обвязочный код (shutdown, инициализация): оставлен `except Exception:` в критических местах с добавлением `exc_info=True` в логирование
  - Обновлен метод `maintenance_message`: заменен `except Exception:` на `except (TelegramError, NetworkError, TimedOut):`
  - Обновлен метод `log_command`: заменены исключения для ошибок отправки на `except (TelegramError, NetworkError, TimedOut):`, добавлен `exc_info=True` для общих ошибок
  - Обновлен метод `start_main_command`: классифицированы исключения по типам, добавлен `exc_info=True` для критических ошибок
  - Обновлен метод `help_command`: заменен `except Exception:` на `except (TelegramError, NetworkError, TimedOut):`
  - Обновлен метод `start`: классифицированы исключения по типам, добавлен `exc_info=True` для warmup ошибок, повторной инициализации и общих ошибок
  - Обновлен метод `stop`: классифицированы исключения по типам, добавлен `exc_info=True` для ошибок остановки updater, приложения и shutdown

- **Приведение SupportBot в соответствие с DI и AppSettings**:
  - Удалена публикация в `bot_data` из метода `start` в `SupportBot`
  - Добавлен комментарий о том, что все зависимости доступны через экземпляр `SupportBot`, `bot_data` больше не используется для DI
  - Интегрирован `AppSettings` в `SupportBot.__init__` для доступа к настройкам через DI
  - Обновлен docstring класса `SupportBot` с упоминанием использования `AppSettings`
  - Заменены все прямые чтения `config.admin_chat_id` на `self.settings.admin_chat_id` в методах `start`, `stop` и `start_main_command`
  - Удалены ленивые импорты `from utils.config import config as _cfg` из методов
  - Импорт `config` оставлен только для `config.telegram_token` в `__init__` (точка входа)

- **Расщепление и удаление CommandHandlers — создание BaseHandlers для общих методов**:
  - Создан базовый класс `BaseHandlers` в `bot/base_handlers.py` с общими утилитарными методами
  - Перенесены общие методы из `CommandHandlers`: `_is_super_admin`, `_safe_reply_text`, `_retry_on_connect_error`, `_extract_target_user_id`, `_send_log_file`
  - Добавлены поля `services: BotServices` и `admins_store: AdminsStore` в `BaseHandlers`
  - Добавлена инициализация `self.logger = get_logger(__name__)` в `BaseHandlers`
  - Перенесена полная реализация пользовательских команд в `UserHandlers`: `start_command`, `help_command`, `frog_command`, `unknown_command`
  - `UserHandlers` теперь наследуется от `BaseHandlers` вместо делегирования в `CommandHandlers`
  - Удалено делегирование и поле `self._core` из `UserHandlers`
  - Обновлен `__init__` в `UserHandlers`: принимает только `services` и `next_run_provider`, инициализирует `BaseHandlers`
  - Перенесена полная реализация административных команд в `AdminHandlers`: `status_command`, `admin_log_command`, `stop_command`, `admin_force_send_command`, `admin_add_chat_command`, `admin_remove_chat_command`, `list_chats_command`, `set_frog_limit_command`, `set_frog_used_command`, `mod_command`, `unmod_command`, `list_mods_command`
  - `AdminHandlers` теперь наследуется от `BaseHandlers` вместо делегирования в `CommandHandlers`
  - Удалено делегирование и поле `self._core` из `AdminHandlers`
  - Обновлен `__init__` в `AdminHandlers`: принимает только `services` и `next_run_provider`, инициализирует `BaseHandlers`
  - Перенесена полная реализация модельных команд в `ModelHandlers`: `set_kandinsky_model_command`, `set_gigachat_model_command`, `list_models_command`
  - `ModelHandlers` теперь наследуется от `BaseHandlers` вместо делегирования в `CommandHandlers`
  - Удалено делегирование и поле `self._core` из `ModelHandlers`
  - Обновлен `__init__` в `ModelHandlers`: принимает только `services` и `next_run_provider`, инициализирует `BaseHandlers`
  - Обновлен `WednesdayBot` для использования только специализированных хендлеров
  - Удалено создание `self.handlers = CommandHandlers(...)` из `WednesdayBot.__init__`
  - Удален импорт `CommandHandlers` из `wednesday_bot.py`
  - Обновлены комментарии в `wednesday_bot.py`, убраны упоминания `CommandHandlers`
  - Обновлены тесты для использования специализированных хендлеров вместо `CommandHandlers`
  - Заменены все создания `CommandHandlers` на соответствующие специализированные хендлеры в `test_handlers.py`
  - Тесты пользовательских команд используют `UserHandlers`
  - Тесты административных команд используют `AdminHandlers`
  - Тесты модельных команд используют `ModelHandlers`
  - Обновлен тест `test_wednesday_bot_initializes_components` для проверки специализированных хендлеров
  - Удалены неиспользуемые импорты `CommandHandlers` из тестов
  - Удален неиспользуемый класс `DummyHandlers` из `test_wednesday_bot.py` (больше не нужен после удаления monkeypatch для `CommandHandlers`)
  - Удален класс `CommandHandlers` из `bot/handlers.py`
  - Файл `bot/handlers.py` оставлен с минимальным содержимым для совместимости с импортами в тестах
  - Обновлен `test_smoke_low_coverage.py` для использования `UserHandlers` вместо `CommandHandlers`
  - Исправлен патч `AdminsStore` в `test_smoke_low_coverage.py` для использования правильного модуля

- **Унификация политики Retry — расширение utils/telegram_retry для поддержки retry_after**:
  - Добавлена обработка `TelegramError` с кодом 429 (rate limit) в функцию `retry_on_connect_error`
  - Добавлен параметр `handle_rate_limit: bool = True` для включения обработки rate limit
  - При обнаружении 429 и `handle_rate_limit=True` функция читает `retry_after` из атрибута ошибки или заголовков ответа
  - Используется `retry_after` как задержка перед следующей попыткой вместо стандартного экспоненциального backoff
  - Сохранена существующая логика для других сетевых ошибок (httpx, NetworkError, TimedOut)
  - Интеграция retry helper в `send_wednesday_frog`: заменён ручной retry-цикл на использование `retry_on_connect_error`
  - Удалён ручной цикл `for attempt in range(...)` и логика backoff/jitter из `send_wednesday_frog`
  - Сохранена обработка успешной отправки (отметка в dispatch_registry, increment счетчиков)
  - Упрощена обработка ошибок: разделение на сетевые/Telegram-ошибки и неожиданные программные ошибки
  - Удалена неиспользуемая константа `RETRY_AFTER_DEFAULT_SECONDS` из `wednesday_bot.py`
  - Классификация исключений в хендлерах: заменены все `except Exception:` на конкретные типы в методах `frog_command`, `stop_command`, `admin_log_command`, `admin_force_send_command`
  - Infrastructure ошибки (retry + мягкая деградация): `except (TelegramError, NetworkError, TimedOut):` для сетевых/Telegram ошибок
  - Programming/Business ошибки: `except (ValueError, TypeError, AttributeError):` для логических ошибок
  - Обвязочный код (shutdown): оставлен `except Exception:` в `stop_command` для фоллбека остановки с добавлением `exc_info=True` в логирование

- **Завершение DI — создание AppSettings для настроек приложения**:
  - Добавлен dataclass `AppSettings` в `services/app_settings.py` для инкапсуляции настроек приложения
  - `AppSettings` содержит поля: `admin_chat_id`, `chat_id`, `scheduler_send_times`, `frog_rate_limit_minutes`, `frog_rate_limit_window_seconds`, `frog_rate_limit_max_requests`, `scheduler_tz`, `time_format_length`
  - Добавлен метод `from_config` для инициализации из глобального `Config`
  - Добавлено поле `settings: AppSettings` в `BotServices` для доступа к настройкам через DI
  - Инициализация `AppSettings` в `WednesdayBot.__init__` через `AppSettings.from_config(config)`
  - Замена чтения `config.scheduler_send_times` на `self.services.settings.scheduler_send_times` в `send_wednesday_frog`
  - Замена чтения `TIME_FORMAT_LENGTH` на `self.services.settings.time_format_length` в `send_wednesday_frog`
  - Замена `config.admin_chat_id` на `self.services.settings.admin_chat_id` в методе `_is_super_admin`
  - Замена прямого чтения `config.admin_chat_id` на `self.services.settings.admin_chat_id` в `stop_command`
  - Замена прямого чтения `config.admin_chat_id` на `self.services.settings.admin_chat_id` в `admin_force_send_command` и `list_mods_command`
  - Удален неиспользуемый импорт `config` из `bot/handlers.py`
  - Добавлено поле `bot_controller: WednesdayBot | None` в `BotServices` для доступа к экземпляру бота через DI
  - Инициализация `bot_controller` в `WednesdayBot.__init__` через `self.services.bot_controller = self`
  - Замена чтения `context.application.bot_data.get("bot")` на `self.services.bot_controller` в `stop_command`
  - Замена сохранения `pending_shutdown_edit` через `bot_instance.pending_shutdown_edit` на `self.services.bot_controller.pending_shutdown_edit`
  - Замена `bot_instance.stop()` на `await self.services.bot_controller.stop()`
  - Обновлен docstring `stop_command`, убрано упоминание `bot_data`
  - Удалена публикация всех зависимостей в `bot_data` в методе `start` (`usage`, `chats`, `metrics`, `prompt_cache`, `user_state_store`, `rate_limiter`, `services`, `bot`)
  - Добавлен комментарий о том, что все зависимости доступны через `BotServices`

- **Горизонтальное масштабирование rate limiting для команды /frog**:
  - Переведён rate limiting команды `/frog` с локальных словарей на Redis через `RateLimiter`
  - Per-user лимит использует ключ `frog:user:{user_id}` с окном `FROG_RATE_LIMIT_MINUTES * 60` секунд и лимитом 1
  - Глобальный лимит использует ключ `frog:global:global` с окном `FROG_RATE_LIMIT_WINDOW_SECONDS` и лимитом `FROG_RATE_LIMIT_MAX_REQUESTS`
  - Сохранена логика пропуска per-user лимита для администраторов
  - Удалены локальные поля `_frog_rate_limit`, `_frog_rate_limit_minutes`, `_global_frog_rate_limit`, `_global_frog_rate_limit_window`, `_global_frog_rate_limit_max` из `CommandHandlers.__init__`
  - Rate limiting теперь поддерживает горизонтальное масштабирование при работе нескольких инстансов бота

- **Обновление документации ARCHITECTURE.md**:
  - Добавлен раздел "Dependency Injection" с описанием использования `BotServices` для всех зависимостей
  - Указано, что `bot_data` больше не используется для DI
  - Описан `AppSettings` как способ доступа к конфигурации через DI
  - Обновлен раздел "Rate Limiting" с указанием, что все лимиты реализуются через `RateLimiter` (Redis)
  - Описана стратегия fail-open при недоступности Redis
  - Добавлен раздел "Retry Policy" с описанием использования `utils/telegram_retry` для PTB-хендлеров и Celery-retry для Celery-тасок
  - Добавлен раздел "Handler Architecture" с описанием структуры `BaseHandlers` → `UserHandlers` / `AdminHandlers` / `ModelHandlers`
  - Указано, что `CommandHandlers` удален
  - Обновлены диаграммы компонентов и sequence-диаграммы для отражения новой архитектуры хендлеров

---

## [6.12.0] 2025-12-16 — Архитектурный рефакторинг хендлеров, DI через BotServices и стабилизация async-I/O

### Изменено

- **Архитектурный рефакторинг хендлеров команд (SoC)**:
  - Добавлены отдельные классы `UserHandlers`, `AdminHandlers` и `ModelHandlers` (`bot/handlers_user.py`, `bot/handlers_admin.py`, `bot/handlers_models.py`), инкапсулирующие пользовательские, административные и модельные команды соответственно с делегированием логики в существующий `CommandHandlers` для сохранения обратной совместимости.
  - `WednesdayBot.setup_handlers()` теперь регистрирует PTB‑хендлеры через специализированные экземпляры (`user_handlers`, `admin_handlers`, `model_handlers`), что явно разделяет зоны ответственности и упрощает навигацию по коду.
  - Конструктор `WednesdayBot` создаёт как базовый `CommandHandlers` (для существующих тестов и Celery‑контекста), так и узкоспециализированные наборы хендлеров, использующие общий контейнер зависимостей `BotServices` и единый `next_run_provider`.

- **Жизненный цикл PTB‑приложений (остановка и shutdown)**:
  - В методе `WednesdayBot.stop()` после `application.stop()` добавлен явный вызов `application.shutdown()` с защитой от исключений, чтобы следовать рекомендуемой последовательности PTB `initialize -> start -> stop -> shutdown` и гарантированно освобождать ресурсы.
  - В методе `SupportBot.stop()` аналогично добавлен вызов `application.shutdown()`, унифицирующий жизненный цикл резервного бота с основным и уменьшающий риск утечек ресурсов при множественных перезапусках.

- **Унификация retry и обработки ошибок Telegram/сети**:
  - Добавлен общий утилитный модуль `utils/telegram_retry.py` с helper-функцией `retry_on_connect_error` и декоратором `retry_on_telegram_error` для повторных попыток при сетевых/Telgram-ошибках.
  - `CommandHandlers` переведён на использование общего helper'а через тонкую обёртку `_retry_on_connect_error`, сохраняя совместимость с существующими тестами и фикстурами, которые патчат этот метод.
  - В `WednesdayBot.send_wednesday_frog` и вспомогательных методах `_send_error_message`, `_send_user_friendly_error`, `_send_admin_error`, `_send_fallback_image` разделены инфраструктурные ошибки Telegram/сети (`TelegramError`/`NetworkError`) и неожиданные программные ошибки, с более точным логированием и без изменения пользовательского поведения.
  - В `CommandHandlers` добавлен вспомогательный метод `_safe_reply_text`, использующий декоратор `@retry_on_telegram_error` для унифицированного retry-паттерна при отправке простых текстовых сообщений в Telegram.

- **Управление зависимостями бота (DI через BotServices)**:
  - Добавлен отдельный контейнер зависимостей `BotServices` (`services/bot_services.py`), инкапсулирующий основные сервисы бота: генератор изображений (`ImageGenerator`), планировщик (`TaskScheduler | None`), хранилища (`UsageTracker`, `ChatsStore`, `DispatchRegistry`, `Metrics`), Redis‑обёртки (`PromptCache`, `UserStateStore`) и `RateLimiter`.
  - `WednesdayBot` в конструкторе собирает все сервисы в единый объект `self.services: BotServices` и использует его как источник зависимостей для обработчиков команд; при этом ключевые объекты продолжают публиковаться в `application.bot_data` (`usage`, `chats`, `metrics`, `prompt_cache`, `user_state_store`, `rate_limiter`, `bot`, `services`) для сохранения обратной совместимости с существующим кодом.
  - `CommandHandlers` переведён на явный DI‑интерфейс `CommandHandlers(services: BotServices, next_run_provider=...)`: внутри обработчиков доступ к хранилищам и метрикам осуществляется через `self.services.usage/chats/metrics`, а не через неявное чтение `context.application.bot_data[...]`, что упрощает статический анализ и модульное тестирование.
  - Обновлены интеграционные и unit‑тесты (`tests/test_bot/test_handlers.py`, `tests/test_smoke_low_coverage.py`): создание `CommandHandlers` теперь выполняется через заглушки `services`/`BotServices`, а тесты, ранее вручную наполнявшие `context.application.bot_data["usage"/"chats"/"metrics"]`, переключены на работу с полями контейнера зависимостей.
  - Обновлён раздел про тестирование обработчиков в `docs/TESTING_GUIDE.md`: примеры конструирования `CommandHandlers` и совет по использованию DI через `BotServices` вместо прямого доступа к `bot_data` для новых тестов и сервисов.

- **Устранение блокирующего файлового I/O в асинхронном коде**:
  - В `ImageGenerator` добавлены асинхронные обёртки `_save_image_async()` и `_get_random_saved_image_async()`, выносящие операции записи/чтения изображений на диск в отдельный поток через `asyncio.get_running_loop().run_in_executor(...)`, чтобы не блокировать event loop.
  - Метод `WednesdayBot.send_wednesday_frog()` переведён на использование `_save_image_async()` при предварительном сохранении сгенерированных изображений в `data/frogs`, что снижает латентность при массовых рассылках.
  - Админская команда `/log` в `CommandHandlers` и резервный бот `SupportBot.log_command` получили вспомогательные async‑методы для чтения лог‑файлов в отдельном потоке перед отправкой документа, устраняя синхронный файловый I/O из hot‑path админских хендлеров.

- **Документация legacy‑паттерна запуска через updater.start_polling**:
  - Docstring метода `WednesdayBot.start()` расширен подробным описанием причины использования последовательности `initialize() -> start() -> updater.start_polling() -> цикл while self.is_running` вместо `application.run_polling()`.
  - В документированном контракте зафиксированы зависимости этого паттерна от деградационного `SupportBot`, внешнего супервизора (CeleryServices, команды /stop) и явного вызова `application.stop()/application.shutdown()`, чтобы упростить будущую миграцию жизненного цикла.

---

## [6.11.0] 2025-12-16 — Доработка команд /mod и /unmod: поддержка reply, ограничение доступа для супер-админа и расширенное тестирование

### Добавлено

- **Helper-методы для работы с админами** (`bot/handlers.py`):
  - Добавлен метод `_extract_target_user_id()` для единого извлечения target_user_id из reply или аргументов команды
  - Добавлен метод `_is_super_admin()` для проверки прав главного администратора

- **Тесты для команд `/mod` и `/unmod`** (`tests/test_bot/test_handlers.py`):
  - Добавлены unit-тесты для `_extract_target_user_id` (reply/аргумент/ошибочные случаи)
  - Добавлены unit-тесты для `_is_super_admin` (проверка супер-админа и не-супер-админа)
  - Добавлены тесты для `/mod`: вызов от не-супер-админа (отказ), с reply, с аргументом
  - Добавлены тесты для `/unmod`: вызов от не-супер-админа (отказ), с reply, с аргументом, попытка удалить главного админа, список админов без аргументов
  - Обновлены существующие тесты для соответствия новой логике проверки супер-админа

### Изменено

- **Команда `/mod`** (`bot/handlers.py`):
  - Ограничен доступ только для главного администратора (Super Admin)
  - Добавлена поддержка reply на сообщение пользователя для указания целевого пользователя
  - Обновлены сообщения об использовании с указанием возможности использования reply
  - Добавлено логирование ключевых шагов выполнения команды

- **Команда `/unmod`** (`bot/handlers.py`):
  - Ограничен доступ только для главного администратора (Super Admin)
  - Добавлена поддержка reply на сообщение пользователя для указания целевого пользователя
  - Реализован режим показа списка всех администраторов при вызове без аргументов/reply
  - Список администраторов включает имена пользователей и username (при наличии)
  - Улучшена защита главного администратора от удаления
  - Добавлено логирование ключевых шагов выполнения команды

- **Команда `/help`** (`bot/handlers.py`):
  - Обновлена справка для `/mod` и `/unmod` с указанием новых возможностей (reply, список админов)
  - Добавлено указание ограничения доступа только для главного администратора

---

## [6.10.0] 2025-12-16 — Миграция команды /frog на Celery для асинхронной обработки

### Добавлено

- **Celery-задача для ручной генерации изображений**:
  - Новая задача `wednesday.send_frog_manual` в `services/celery_tasks.py` для асинхронной обработки команды `/frog`
  - Задача выполняет генерацию изображения, отправку пользователю, сохранение локально и инкремент usage-счётчика
  - Реализована fallback-логика с отправкой случайного изображения из архива при ошибках генерации
  - Уведомление администраторов при критических ошибках с детальной информацией
  - Автоматический retry только для сетевых ошибок через `is_retryable_error()`
  - Поддержка удаления статусного сообщения после успешной отправки

### Изменено

- **Обработчик команды `/frog`** (`bot/handlers.py`):
  - Рефакторинг обработчика для использования Celery-задачи вместо блокирующего выполнения
  - Обработчик теперь выполняет только валидацию (rate limits, месячный лимит) и постановку задачи в очередь
  - Значительно сокращено время обработки команды (с нескольких секунд до миллисекунд)
  - Event Loop больше не блокируется генерацией и отправкой изображений
  - Улучшена масштабируемость через распределение нагрузки на Celery workers
- **Маршрутизация Celery-задач** (`services/celery_app.py`):
  - Добавлена маршрутизация задачи `wednesday.send_frog_manual` в очередь `wednesday`
- **Документация**:
  - Обновлён `docs/API_REFERENCE.md`: изменено описание команды `/frog` для отражения использования Celery вместо синхронного выполнения
  - Обновлён `docs/ARCHITECTURE.md`: заменена диаграмма синхронного потока `/frog` на диаграмму асинхронного потока с Celery; обновлён раздел "Потоки данных" с описанием использования Celery
  - Обновлён `docs/MONITORING.md`: добавлены примеры метрик для задачи `wednesday.send_frog_manual` для мониторинга ручных генераций
- **Совместимость с Python 3.14**:
  - Обновлён тип аннотации параметра `metrics` в `ImageGenerator.generate_frog_image()` так, чтобы избежать `TypeError` при импорте модуля на Python 3.14
- **Тесты команды `/frog`**:
  - Актуализированы unit‑тесты `tests/test_bot/test_handlers.py` под новую асинхронную реализацию `/frog` через Celery‑задачу `wednesday.send_frog_manual`: проверяется постановка задачи в очередь, соблюдение rate limit и месячных лимитов, а также отсутствие постановки задачи при превышении лимита
- **Фикстура Telegram‑обновлений в тестах**:
  - Расширена фикстура `fake_update` в `tests/conftest.py` (добавлены `chat_id` и `message_id` для статусных сообщений), чтобы тесты корректно покрывали удаление статусных сообщений и передачу `status_message_id` в Celery‑задачу при обработке `/frog`

---

## [6.9.0] 2025-12-15 — Автоматическая документация MkDocs/mkdocstrings, стабилизация ссылок и проверка сборки docs в CI

### Добавлено

- **Инфраструктура MkDocs**:
  - Конфигурация `mkdocs.yml` c темой Material, навигацией по основным документам и русской локалью.
  - Подключение `mkdocstrings[python]` для автоматического извлечения API-документации из docstrings.
  - Новый авто‑генерируемый справочник `docs/API_REFERENCE_AUTO.md` c разделами для `bot.handlers.CommandHandlers`, `services.image_generator.ImageGenerator`, `services.celery_tasks`, `bot.wednesday_bot.WednesdayBot`, `services.scheduler.TaskScheduler` и ключевых утилит.
  - Главная страница документации `docs/index.md` с навигацией по разделам.
- **Интеграция в пайплайн разработки**:
  - Цели `docs-serve`, `docs-build` и алиас `docs` в `Makefile` для локального просмотра и сборки документации (`mkdocs serve`/`mkdocs build`).
- **Структура docs/**:
  - Символические ссылки из корня репозитория в `docs/` для включения внешних Markdown-файлов в сайт без дублирования содержимого (например, история изменений и руководство по тестам).
- **CI для документации**:
  - Reusable workflow `.github/workflows/jobs/check-docs.yml` для сборки документации через `make docs-build` в GitHub Actions.

### Изменено

- **Якоря и внутренние ссылки**:
  - Для ключевых документов (`docs/INSTALLATION.md`, `docs/DEPLOYMENT.md`, `docs/TESTING_GUIDE.md`, `docs/MONITORING.md`) добавлены явные стабильные ASCII-якоря в формате `{#anchor-id}` и обновлены все внутренние ссылки, чтобы использовать новые ID.
  - Удалены относительные ссылки, выходящие за пределы `docs/` (типа `../...`), ссылки приведены к внутренним путям MkDocs с учётом новой структуры.
  - Обновлены ссылки в `docs/PROJECT_SUMMARY.md` и релиз-нотах для согласованности с корнем документации `docs/`.
- **Зависимости**:
  - В `requirements.txt` и `pyproject.toml` добавлены зависимости `mkdocs`, `mkdocstrings[python]` и `mkdocs-material` для поддержки новой системы документации.
  - В `requirements.txt` добавлен `mkdocs-link-check` для проверки ссылок при сборке документации.
- **CI пайплайн**:
  - Цели `ci` и `ci-full` в `Makefile` расширены шагом `docs-build` для проверки успешной сборки документации как части локального CI.
  - Основной workflow `.github/workflows/ci.yml` дополнен job `check-docs`, использующим reusable workflow для сборки документации в GitHub Actions.
  - В `.github/workflows/ci.yml` добавлен job `deploy-docs`, который разворачивает собранную документацию на GitHub Pages только при `push` в ветку `main` после успешного прохождения всех проверок.
  - Добавлен reusable workflow `.github/workflows/jobs/deploy-docs.yml`, отвечающий за установку зависимостей и запуск `mkdocs gh-deploy --force` в отдельном шаге CI.

---

## [6.8.0] 2025-12-15 — Документация архитектуры, развертывания, API, мониторинга, логирования и тестирования: добавлены ARCHITECTURE.md, DEPLOYMENT.md, API_REFERENCE.md, MONITORING.md, LOKI_PROMTAIL_SCHEMA.md; обновлены TYPING_GUIDE.md и TESTING_GUIDE.md

### Добавлено

- **Документация архитектуры** (`docs/ARCHITECTURE.md`):
  - Полное описание высокоуровневой архитектуры проекта Wednesday Frog Bot
  - Описание основных слоев: интерфейсный, бизнес-логика, хранилище данных, асинхронные задачи
  - Детальное описание всех компонентов системы:
    - BotRunner (супервизор, управление жизненным циклом ботов)
    - WednesdayBot и SupportBot (разделение ответственности)
    - Handlers (обработка команд)
    - Services (ImageGenerator, RateLimiter, PromptCache, UserStateStore, TaskScheduler)
    - Workers (Celery App, Beat, Tasks)
  - Три Mermaid-диаграммы:
    - **Component Diagram** — общая схема компонентов и их взаимодействие
    - **Sequence Diagram** — поток данных при генерации изображения по команде `/frog`
    - **Flowchart** — поток автоматической отправки через Celery Beat
  - Разделы с описанием потоков данных, хранилищ (PostgreSQL, Redis), мониторинга, безопасности и масштабирования
  - Описание Dependency Injection (DI) — ручная инициализация зависимостей через конструкторы и фабрики
  - Раздел "Конфигурация" — описание подхода 12 Factor App, источники конфигурации (переменные окружения, `.env`, secret-файлы)
  - Уточнение про Lazy Initialization в Celery — важность для fork safety и предотвращения утечек ресурсов
  - Описание схемы миграций PostgreSQL — идемпотентный подход с `CREATE TABLE IF NOT EXISTS`
- **Руководство по развертыванию** (`docs/DEPLOYMENT.md`):
  - Полное руководство по развертыванию бота в production среде с использованием Docker Compose
  - Раздел "Требования к инфраструктуре": минимальные требования к CPU/RAM, список требуемых сервисов (Docker, Docker Compose, PostgreSQL, Redis)
  - Продакшен Docker Compose конфигурация: пример файла `docker-compose.yml` с сервисами `bot`, `celery-worker`, `celery-beat`, `postgres`, `redis`, `prometheus`
  - Обязательные volumes для персистентных данных: `postgres_data`, `redis_data`, `frog_images`, `prompt_storage`, `beat_data`
  - Конфигурация Prometheus Exporter для сбора метрик
  - Важное замечание: Celery Workers и Celery Beat используют один образ с разными командами
  - Раздел "Настройка окружения": описание файла `.env`, критические переменные окружения (токены Telegram, Kandinsky/GigaChat, PostgreSQL/Redis, `ADMIN_CHAT_ID`)
  - Управление секретами: рекомендации по использованию Docker Secrets, переменных окружения хоста, HashiCorp Vault
  - Процедура развертывания (первый запуск): клонирование репозитория, сборка образа, миграция БД (варианты через временный контейнер или docker-compose), запуск сервисов
  - Обновление бота без downtime: стратегия rolling update с масштабированием worker, команды для обновления только сервисов приложения
  - Backup и Restore: инструкции по созданию дампа PostgreSQL, архивации Docker Volumes, полному backup с автоматизацией через скрипты
  - Troubleshooting: решения распространенных проблем:
    - Бот не отвечает (проверка логов, healthcheck, подключение к Telegram API)
    - Celery не запускается (проверка подключения к Redis, паролей)
    - Ошибки миграции (проверка версии PostgreSQL, прав доступа)
    - Высокое использование ресурсов (оптимизация лимитов, concurrency)
    - Проблемы с генерацией изображений (проверка API ключей, сетевых подключений)
- **Справочник команд API** (`docs/API_REFERENCE.md`):
  - Полный справочник команд для Telegram-бота "Wednesday Frog Bot"
  - Раздел "Обзор и условные обозначения": объяснение синтаксиса команд, обозначения обязательных и необязательных аргументов
  - Пользовательские команды: подробное описание `/start`, `/help`, `/frog` с примерами использования, rate limits и ограничений
  - Административные команды (15 команд): полное описание всех админ-команд с синтаксисом, параметрами и примерами:
    - `/status` — расширенный статус бота и проверка систем
    - `/log` — получение логов
    - `/force_send` — принудительная отправка изображений
    - Управление чатами (`/add_chat`, `/remove_chat`, `/list_chats`)
    - Управление моделями (`/set_kandinsky_model`, `/set_gigachat_model`, `/list_models`)
    - Управление администраторами (`/mod`, `/unmod`, `/list_mods`)
    - Управление лимитами (`/set_frog_limit`, `/set_frog_used`)
    - `/stop` — остановка бота
  - Команды Support Bot: описание функционала резервного бота (`/start`, `/help`, `/log`, обработка неизвестных команд)
  - Взаимодействие в группах: автоматическое добавление/удаление, использование команд в группах, приветственные сообщения
  - Инлайн-режим: указание, что режим не поддерживается
  - Дополнительная информация: rate limiting, автоматические рассылки, обработка ошибок, получение ID чата/пользователя
  - FAQ: ответы на частые вопросы пользователей
  - Документ предназначен для конечных пользователей и администраторов, написан на русском языке
- **Руководство по мониторингу** (`docs/MONITORING.md`):
  - Полное описание стека наблюдаемости (Observability Stack) для Wednesday Frog Bot
  - Раздел "Обзор стека наблюдаемости": описание компонентов (Prometheus, Grafana, Loki, Promtail) и их интеграция с Docker Compose через сеть `monitoring`
  - Схема потока данных: визуализация сбора метрик и логов от приложения до Grafana
  - Раздел "Мониторинг метрик (Prometheus & Grafana)":
    - Полный список доступных метрик с описанием и примерами:
      - Метрики генерации изображений (`frog_generations_total`, `frog_generation_latency_seconds`, `frog_generation_queue_length`)
      - Метрики Celery задач (`celery_tasks_total`, `celery_task_duration_seconds`, `celery_queue_length`, `celery_active_tasks`)
      - Метрики HTTP retry (`http_retries_total`, `http_retry_wait_seconds`)
    - Описание ключевых панелей Grafana: Wednesday App Metrics, Wednesday Celery Metrics, Wednesday Retry Metrics, Wednesday Logs Dashboard
    - Предложенные SLO (Service Level Objectives):
      - Доступность генераций (99% успешных)
      - Латентность генераций (99% < 30 секунд)
      - Доступность сервиса (99.9% uptime)
      - Обработка очереди Celery (не более 50 задач)
  - Раздел "Логирование (Loki & Promtail)":
    - Описание структуры JSON-логов с полями `timestamp`, `level`, `message`, `name`, `function`, `line`, `extra`
    - Детальное описание работы Promtail: сбор логов из Docker контейнеров, парсинг JSON, извлечение labels
    - 8 полезных запросов LogQL для диагностики:
      - Поиск ошибок 5xx для `/generate`
      - Фильтрация логов по `user_id` и `chat_id`
      - Поиск ошибок генерации и healthcheck failures
      - Поиск логов с высокой латентностью
      - Подсчет генераций по статусу
  - Раздел "Алерты (Alerting)":
    - 7 критических правил для Prometheus Alertmanager:
      - Celery Queue Overload (очередь > 50 задач)
      - High Generation Latency (P99 > 45 секунд)
      - Service Down (healthcheck недоступен)
      - Database Connection Error (частые ошибки PostgreSQL)
      - High Generation Error Rate (>5% ошибок)
      - Celery Task Failures
      - Exporter Down
    - Описание каналов уведомлений: Telegram, Email, PagerDuty, Webhook с примерами конфигурации Alertmanager
    - Рекомендации по настройке: Critical → Telegram + Email + PagerDuty, Warning → Telegram + Email
  - Раздел "Конфигурация":
    - Описание расположения всех конфигурационных файлов в директории `monitoring/`
    - Детальное описание конфигураций Prometheus, Loki, Promtail, Grafana
    - Описание переменных окружения для настройки мониторинга
    - Инструкции по обновлению конфигураций без перезапуска (где применимо)
  - Документ предназначен для DevOps-инженеров и администраторов, написан на русском языке
- **Справочник по схеме структурированного логирования** (`docs/LOKI_PROMTAIL_SCHEMA.md`):
  - Детальный справочник по схеме структурированного JSON-логирования для эффективного использования Loki и Promtail
  - Раздел "Обзор структуры лога": описание JSON-формата, процесса сбора логов Promtail из Docker stdout/stderr, полная структура JSON-записи с примерами
  - Раздел "Обязательные поля (Standard Fields)": полное описание всех стандартных полей, автоматически добавляемых loguru:
    - Временные метки (`time.repr`, `time.timestamp`)
    - Уровни логирования (`level.name`, `level.no`)
    - Сообщения (`message`) с автоматической маскировкой секретов
    - Информация о месте вызова (`file`, `function`, `line`, `module`, `name`)
    - Информация о процессе (`process`, `thread`)
    - Дополнительные поля (`extra`) со структурированными данными
  - Раздел "Ключевые поля-метки (Loki Labels)": детальное описание текущих Loki labels (`service`, `env`, `level`) и объяснение, почему высококардинальные поля (`user_id`, `prompt_hash`, `task_id`, `request_id`, `message`, `timestamp`) не используются как labels
  - Рекомендации по добавлению новых labels: критерии оценки кардинальности, примеры хороших и плохих candidates для labels
  - Раздел "Поля, специфичные для бота": полное описание всех полей, используемых в проекте:
    - Поля событий (`log_event`): `event`, `status`, `service`, `env`, `user_id`, `prompt_hash`, `image_id`, `latency_ms`
    - Поля Celery задач (`log_worker`): `task_name`, `task_id`
    - Поля HTTP-запросов (`log_http`): `method`, `path`, `status_code`
    - Поля обработчиков бота: `handler`, `chat_id`
    - Потенциальные поля для будущего использования: `request_id`, `api_endpoint`
  - Раздел "Примеры использования": 3 полных примера JSON-логов (обычное событие, кеширование изображения, Celery задача) и 10 практических примеров LogQL-запросов для различных сценариев поиска и анализа
  - Раздел "Гарантии по безопасности": описание автоматической маскировки секретов через `mask_secrets()` и `scrub()`, список чувствительных ключевых слов, рекомендации по операционной безопасности
  - Раздел "Конфигурация Promtail": описание текущей конфигурации Promtail с pipeline stages для парсинга Docker JSON-file формата и извлечения полей
  - Раздел "Эволюция схемы": рекомендации по версионированию, добавлению новых полей, изменению структуры JSON и потенциальным улучшениям (добавление `event`, `status`, `handler`, `task_name` в Loki labels)
  - Справочная информация: описание основных функций логирования, ссылки на связанные документы и полезные ресурсы
  - Документ предназначен для разработчиков и DevOps-инженеров, работающих с логированием и мониторингом, написан на русском языке
- **Документация кода (docstrings)** (`services/`):
  - Проведён полный аудит и добавлены стандартизированные docstrings в формате Google Style для всех публичных классов, методов и функций в директории `services/`
  - Документированы все сервисы бизнес-логики:
    - `celery_tasks.py` — класс `CeleryServices` и все Celery задачи (send_wednesday_frog_task, generate_frog_image_task, daily_cleanup_task, daily_statistics_task, beat_heartbeat)
    - `healthcheck.py` — все функции проверки зависимостей (_check_redis, _check_postgres, _check_metrics_stream, _check_celery) и эндпоинт `/health`
    - `image_generator.py` — класс `ImageGenerator` и все публичные методы (generate_frog_image, check_api_status, get_random_caption, save_image_locally, get_random_saved_image)
    - `prompt_cache.py` — класс `PromptCache` и все методы кэширования (set, get, delete, exists, keys)
    - `prompt_generator.py` — класс `PromptStorage` и методы работы с файловым хранилищем (save_prompt, get_random_prompt)
    - `rate_limiter.py` — классы `RateLimiter` и `CircuitBreaker` со всеми методами управления лимитами и circuit breaker
    - `scheduler.py` — класс `TaskScheduler` и все методы планирования задач (schedule_wednesday_task, schedule_daily_task, schedule_interval_task, start, stop, get_next_run, clear_all_jobs, get_jobs_count)
    - `user_state_store.py` — класс `UserStateStore` и методы работы с состоянием пользователей (set_state, get_state, clear_state)
  - Документированы все клиенты внешних ML-сервисов (`services/clients/`):
    - `factory.py` — функции создания клиентов (create_image_client, create_text_client)
    - `gigachat_text.py` — класс `GigaChatTextClient` и все методы интерфейса ITextToTextClient (generate, check_api_status, get_available_models, set_model, aclose)
    - `kandinsky.py` — класс `KandinskyClient` и все методы интерфейса ITextToImageClient (generate, check_api_status, get_available_models, set_model, aclose)
    - `image_client_container.py` — класс `ImageClientContainer` и все методы проксирования и управления клиентом
    - `text_client_container.py` — класс `TextClientContainer` и все методы проксирования и управления клиентом
  - Все docstrings включают:
    - Краткое описание назначения класса/метода
    - Args: описание всех параметров с типами и назначением
    - Returns: описание возвращаемых значений с типами
    - Raises: перечисление возможных исключений (где применимо)
    - Note: дополнительные примечания о поведении, особенностях реализации и использовании
  - Документация готова для автоматической генерации через Sphinx или MkDocs
  - Улучшена читаемость кода и упрощён онбординг новых разработчиков
- **Документация кода (docstrings)** (`bot/`):
  - Проведён полный аудит и добавлены стандартизированные docstrings в формате Google Style для всех публичных хендлеров, функций и классов в директории `bot/`
  - Документированы все обработчики команд (`bot/handlers.py`):
    - Класс `CommandHandlers` с полным описанием всех доступных команд
    - Пользовательские команды: `start_command`, `help_command`, `frog_command`, `unknown_command`
    - Административные команды: `status_command`, `admin_log_command`, `admin_force_send_command`, `admin_add_chat_command`, `admin_remove_chat_command`, `list_chats_command`, `set_kandinsky_model_command`, `set_gigachat_model_command`, `mod_command`, `unmod_command`, `list_mods_command`, `list_models_command`, `set_frog_limit_command`, `set_frog_used_command`, `stop_command`
    - Вспомогательные методы: `_retry_on_connect_error`
  - Документированы все компоненты бота (`bot/wednesday_bot.py`):
    - Класс `WednesdayBot` с описанием жизненного цикла и функциональности
    - Методы жизненного цикла: `__init__`, `start`, `stop`, `setup_handlers`, `setup_scheduler`
    - Основные методы: `send_wednesday_frog`, `get_bot_info`
    - Вспомогательные методы: `_send_error_message`, `_send_user_friendly_error`, `_send_admin_error`, `_send_fallback_image`, `_check_chat_access`, `_handle_error`, `on_my_chat_member`
  - Документированы все компоненты резервного бота (`bot/support_bot.py`):
    - Класс `SupportBot` с описанием назначения и функциональности
    - Методы жизненного цикла: `__init__`, `start`, `stop`, `setup_handlers`
    - Хендлеры команд: `start_main_command`, `help_command`, `log_command`, `maintenance_message`
    - Вспомогательные методы: `_is_admin`
  - Все docstrings для хендлеров включают:
    - Краткое описание команды или события, которое обрабатывается
    - Args: описание параметров `update` (событие от Telegram) и `context` (контекст бота)
    - Side Effects: краткое описание ключевых сервисов и операций, которые вызываются (например, `RateLimiter.check()`, `ImageGenerator.generate_frog_image()`, `Celery.add_task()`)
    - Raises: возможные исключения (где применимо)
  - Все docstrings для вспомогательных методов включают:
    - Краткое описание назначения метода
    - Args: описание всех параметров с типами и назначением
    - Returns: описание возвращаемых значений с типами (где применимо)
    - Raises: перечисление возможных исключений (где применимо)
    - Side Effects: описание операций с побочными эффектами (где применимо)
  - Документация готова для автоматической генерации через Sphinx или MkDocs
  - Улучшена читаемость кода и упрощён онбординг новых разработчиков
  - Специальное внимание уделено описанию параметров `update` и `context` из `python-telegram-bot` для лучшего понимания интерфейса обработчиков
- **Документация кода (docstrings)** (`utils/`):
  - Проведён полный аудит и добавлены стандартизированные docstrings в формате Google Style для всех публичных классов, методов и функций в директории `utils/`
  - Документированы все хранилища данных (`utils/*_store.py`):
    - `admins_store.py` — класс `AdminsStore` и все методы управления администраторами (is_admin, add_admin, remove_admin, list_admins, list_all_admins)
    - `chats_store.py` — класс `ChatsStore` и методы работы со списком чатов (add_chat, remove_chat, list_chat_ids)
    - `images_store.py` — классы `ImagesStore`, `ImageRecord` и методы работы с изображениями (get_by_prompt_hash, load_image_bytes, get_or_create_image)
    - `models_store.py` — класс `ModelsStore` и методы управления моделями Kandinsky и GigaChat (set_kandinsky_model, get_kandinsky_model, set_gigachat_model, get_gigachat_model, set/get_available_models)
    - `prompts_store.py` — классы `PromptsStore`, `PromptRecord` и методы работы с промптами (get_or_create_prompt, get_prompt_by_hash, get_random_prompt)
    - `usage_tracker.py` — класс `UsageTracker` и методы отслеживания использования (increment, get_month_total, can_use_frog, get_limits_info, set_month_total, set_frog_threshold)
  - Документированы все утилиты конфигурации и инфраструктуры:
    - `config.py` — класс `Config` со всеми свойствами конфигурации, классы `ImageConfig` и `SchedulerConfig`, вспомогательные функции (_load_dotenv_if_needed, _validate_required_vars, _get_env_var)
    - `paths.py` — функции разрешения путей (resolve_frog_images_dir, resolve_logs_dir, resolve_prompts_dir)
    - `postgres_client.py` — функции управления пулом подключений PostgreSQL (init_postgres_pool, get_postgres_pool, close_postgres_pool, ensure_database)
    - `postgres_schema.py` — функция инициализации схемы БД (ensure_schema)
    - `redis_client.py` — класс `_InMemoryRedis` и функции управления Redis-клиентом (init_redis_pool, get_redis, close_redis, redis_available, safe_redis_call, get_redis_url)
  - Документированы все утилиты логирования и метрик:
    - `logger.py` — класс `LoguruHandler`, функции настройки логирования (setup_logger, get_logger), функции маскировки секретов (mask_secrets, scrub), функции структурированного логирования (log_event, log_http, log_worker), декораторы логирования (log_execution, log_all_methods)
    - `metrics.py` — класс `Metrics` и все методы метрик (increment_generation_success, increment_generation_failed, add_generation_time, get_summary и др.), функция `record_metric`, функции аналитики (get_daily_generation_stats, get_top_prompts)
    - `prometheus_metrics.py` — функция обновления метрик очереди (set_generation_queue_length)
  - Документированы утилиты для работы с внешними сервисами:
    - `retry.py` — классы и функции retry-механик (_RetryIfNetworkError, _should_retry_http_error), декораторы retry (retry_critical, retry_standard, retry_optional, retry_with_logging)
    - `dispatch_registry.py` — класс `DispatchRegistry` и методы реестра отправок (is_dispatched, mark_dispatched, cleanup_old)
  - Все docstrings включают:
    - Краткое описание назначения класса/функции/метода
    - Args: описание всех параметров с типами и назначением
    - Returns: описание возвращаемых значений с типами
    - Raises: перечисление возможных исключений (где применимо)
  - Документация готова для автоматической генерации через Sphinx или MkDocs
  - Улучшена читаемость кода и упрощён онбординг новых разработчиков
  - Особое внимание уделено описанию работы с базами данных (PostgreSQL, Redis), конфигурацией и утилитами логирования
- **Руководство по типизации** (`docs/TYPING_GUIDE.md`): полностью обновлено и актуализировано для отражения современных практик типизации Python 3.11+
  - Обновлена информация о конфигурации mypy: указано, что конфигурация находится в `pyproject.toml`, а не в устаревшем `mypy.ini`
  - Добавлен раздел "Стандарты импорта" с рекомендациями по использованию `from __future__ import annotations` и стандартных типов (`dict`, `list`) вместо `Dict`, `List` из `typing`
  - Добавлен раздел "Обработка сложных типов":
    - Детальное описание типизации Celery Tasks с примерами из проекта (использование `Task` из `celery`, типизация параметров и возвращаемых значений, декораторы)
    - Описание Dependency Injection через `Protocol` с примерами интерфейсов `ITextToImageClient` и `ITextToTextClient` из проекта
    - Рекомендации по использованию оператора `|` вместо `Optional` и `Union` (современный стиль Python 3.10+)
  - Добавлен раздел "Пользовательские типы и псевдонимы" с описанием использования `TypeAlias` для сложных структур (примеры `RedisBackend` из проекта)
  - Добавлен раздел "Специфика фреймворка Telegram Bot" с описанием типизации обработчиков (`Update`, `ContextTypes.DEFAULT_TYPE`) и примеров из кода проекта
  - Обновлен раздел "Настройка MyPy" с актуальной информацией о конфигурации в `pyproject.toml`, исключениях и использовании `# type: ignore`
  - Добавлены примеры кода из реальных файлов проекта (`bot/`, `services/`, `utils/`) для лучшего понимания практик
  - Документ теперь служит полным справочником по типизации для разработчиков проекта, отражая актуальные практики и стандарты кодовой базы
- **Руководство по тестированию** (`docs/TESTING_GUIDE.md`): полностью обновлено и расширено для описания методологии тестирования сложной архитектуры с PostgreSQL, Redis, Celery и внешними API
  - Добавлен раздел "Инструменты и Среда":
    - Описание используемых инструментов (pytest, pytest-asyncio, pytest-cov, pytest-xdist, unittest.mock)
    - Конфигурация pytest в `pyproject.toml` с описанием всех маркеров тестов
    - Инструкции по запуску тестов: локальный запуск (unit/integration/e2e), запуск через Docker Compose, параллельный запуск с pytest-xdist
    - Описание работы с покрытием кода (pytest-cov): запуск с покрытием, просмотр отчётов, стандарты покрытия
  - Добавлен раздел "Мокирование внешних зависимостей":
    - **PostgreSQL**: описание четырёх подходов к мокированию БД:
      - Фикстуры для очистки таблиц (`cleanup_tables`) — для integration-тестов с полной изоляцией
      - Транзакционный rollback (`postgres_transaction`) — для быстрых тестов без проверки commit'ов
      - In-memory хранилища для unit-тестов (`_InMemoryModelsStore`) — автоматическая подмена через `patch_models_store`
      - Мокирование DAO/ORM слоёв через `unittest.mock` для изоляции бизнес-логики
    - **Redis/Celery**: описание подходов к мокированию:
      - In-memory Redis (`_InMemoryRedis`) для unit-тестов — не требует запущенного Redis
      - Мокирование Celery tasks через `unittest.mock` с обходом декораторов `@celery_app.task`
      - Изоляция Celery очередей для E2E тестов через фикстуру `celery_test_queues` — уникальные очереди для параллельного запуска
    - **Внешние API (Kandinsky/GigaChat)**: описание четырёх подходов:
      - Структурные моки (Protocol-based) — использование `MockTextToImageClient` и `MockTextToTextClient` из `tests/_doubles/clients.py` для типобезопасного мокирования
      - Мокирование HTTP-сессий — подмена `aiohttp.ClientSession` для тестирования клиентов напрямую
      - Мокирование через pytest-mock — использование `mocker` фикстуры для сложных сценариев
      - Мокирование конкретных методов клиента — частичное мокирование через `monkeypatch`
  - Добавлен раздел "Тестирование бизнес-логики (services/)":
    - Описание Dependency Injection для подмены зависимостей через конструкторы сервисов
    - Примеры тестирования сервисов с внешними зависимостями (PromptGenerator, RateLimiter)
    - Тестирование асинхронных сервисов с `@pytest.mark.asyncio`
    - Тестирование сервисов с интеграцией БД — примеры использования `cleanup_tables` для проверки кеширования
  - Добавлен раздел "Тестирование обработчиков (bot/)":
    - Симуляция событий Telegram через фикстуры `fake_update` и `fake_context` — описание структуры и использования
    - Тестирование команд с аргументами — примеры установки `fake_context.args` и проверки ответов
    - Тестирование FSM-переходов — мокирование состояния пользователя через `fake_context.user_data`
    - Тестирование обработчиков с реальными хранилищами — integration-тесты с PostgreSQL через `cleanup_tables`
    - Мокирование retry-механизмов — использование фикстуры `async_retry_stub` для упрощения тестов
  - Добавлен раздел "Фикстуры (Fixtures)" с полным описанием всех фикстур из `conftest.py`:
    - **Autouse фикстуры**: `session_env_defaults`, `base_env`, `patch_models_store` — применяются автоматически
    - **Opt-in фикстуры**: подробное описание с примерами использования:
      - `cleanup_tables` — очистка таблиц PostgreSQL (требует `@pytest.mark.db`)
      - `postgres_transaction` — транзакционный rollback (требует `@pytest.mark.db`)
      - `async_postgres_pool` — session-фикстура для пула соединений
      - `celery_test_queues` — изоляция очередей Celery (требует `@pytest.mark.e2e` и `@pytest.mark.celery`)
      - `celery_worker_ready` — ожидание готовности Celery worker (требует `@pytest.mark.e2e` и `@pytest.mark.celery`)
      - `reset_singletons` — сброс состояния синглтонов
      - `fake_update` и `fake_context` — моки для событий Telegram
      - `async_retry_stub` — отключение retry-механизма
      - `gigachat_client` — создание GigaChat клиента с автоматическим закрытием
      - `reload_config` — перезагрузка конфигурации
  - Все разделы содержат практические примеры кода из реальных тестов проекта
  - Документ теперь служит полным руководством по написанию тестов для разработчиков, описывая все аспекты тестирования сложной архитектуры с изоляцией зависимостей

### Улучшено

- Документация проекта: добавлены централизованные документы с полным описанием архитектуры, процесса развертывания, API и мониторинга для разработчиков, DevOps и пользователей
- Понимание системы: диаграммы визуализируют взаимодействие компонентов и потоки данных
- Онбординг новых разработчиков: ARCHITECTURE.md служит отправной точкой для изучения проекта
- Развертывание в production: DEPLOYMENT.md предоставляет пошаговые инструкции для безопасного и надежного развертывания бота
- Управление инфраструктурой: документированы процедуры backup/restore, обновления без downtime, troubleshooting
- Пользовательская документация: API_REFERENCE.md предоставляет полный справочник всех команд бота с примерами использования, что упрощает работу пользователей и администраторов
- Мониторинг и наблюдаемость: MONITORING.md предоставляет полное руководство по настройке и использованию стека наблюдаемости (Prometheus, Grafana, Loki, Promtail), включая описание всех метрик, дашбордов Grafana, правил алертов и запросов LogQL для диагностики проблем
- Настройка мониторинга: документированы все конфигурационные файлы, переменные окружения и процедуры обновления компонентов мониторинга
- Стандартизация логирования: LOKI_PROMTAIL_SCHEMA.md предоставляет детальный справочник по схеме структурированного JSON-логирования, описывающий все обязательные поля, Loki labels, поля специфичные для бота, примеры использования и рекомендации по расширению схемы, что упрощает эффективное использование Loki и Promtail для поиска и анализа логов
- SLO и алертинг: определены Service Level Objectives и критические правила алертов для обеспечения надежности сервиса
- Документация кода: добавлены полные docstrings в формате Google Style для всех публичных классов и методов в директориях `services/`, `bot/` и `utils/`, что упрощает понимание API сервисов, обработчиков команд и утилит, автоматическую генерацию документации и онбординг новых разработчиков
- Руководство по типизации: `TYPING_GUIDE.md` полностью обновлено с актуальными практиками типизации Python 3.11+, включая современный синтаксис (`|` вместо `Union`), типизацию Celery Tasks, использование `Protocol` для DI, и примеры из реального кода проекта, что упрощает поддержание тип-безопасности и онбординг новых разработчиков
- Руководство по тестированию: `TESTING_GUIDE.md` полностью обновлено и расширено с детальным описанием методологии тестирования сложной архитектуры, включая разделы по мокированию PostgreSQL/Redis/Celery/внешних API, тестированию бизнес-логики через Dependency Injection, тестированию обработчиков Telegram-бота, и полному описанию всех фикстур с примерами использования, что значительно упрощает написание тестов и обеспечение высокой степени изоляции
- Документация обработчиков команд: все хендлеры Telegram-бота теперь имеют полные docstrings с описанием параметров `update` и `context`, side effects и возможных исключений, что значительно упрощает работу с кодом и понимание поведения бота
- Документация утилит: все вспомогательные классы и функции в директории `utils/` теперь имеют полные docstrings с описанием работы с базами данных, конфигурацией, логированием и метриками, что упрощает понимание инфраструктурного слоя приложения
- **Краткий обзор проекта** (`docs/PROJECT_SUMMARY.md`): полностью переписан и актуализирован для отражения текущей архитектуры проекта
  - Удалена устаревшая информация о JSON-файлах и синхронном коде
  - Добавлена секция "Цель проекта" с кратким описанием Wednesday Frog Bot
  - Обновлена секция "Ключевые технологии" с явным указанием стека: Python (Asyncio), PostgreSQL, Redis, Celery, Docker
  - Добавлена секция "Ключевой функционал" с описанием основных возможностей (генерация изображений, планирование задач, администрирование, rate limiting)
  - Добавлена секция "Сравнение: Старое vs Новое" с описанием эволюции проекта (JSON → PostgreSQL, Синхронный код → Asyncio + Celery, Встроенный планировщик → Celery Beat)
  - Добавлена секция "Навигация" со ссылками на ARCHITECTURE.md, README.md и другие документы
  - Файл теперь служит кратким введением перед чтением детальной документации архитектуры
- **Инструкция по установке** (`docs/INSTALLATION.md`): полностью переработана для соответствия современной архитектуре проекта с Docker Compose, PostgreSQL и Redis
  - Сосредоточена на быстром локальном запуске для разработки с использованием Docker Compose
  - Обновлены требования: Docker, Docker Compose, Python 3.10+ (для локальных скриптов)
  - Добавлен раздел "Шаг 1: Клонирование и Конфигурация" с инструкциями по созданию `.env` из `env_example.txt` и настройке файлов secrets для PostgreSQL и Redis
  - Добавлен раздел "Шаг 2: Сборка и Запуск" с описанием команды `docker compose up -d --build` и списком запускаемых сервисов (bot, postgres, redis, celery_worker, celery_beat)
  - Добавлен раздел "Шаг 3: Миграция Базы Данных" с инструкциями по выполнению миграций через `docker compose run --rm bot python3 -m utils.postgres_schema`
  - Добавлен раздел "Шаг 4: Тестирование" с инструкциями по запуску тестов через Makefile
  - Добавлен раздел "Дальнейшие шаги" со ссылками на ARCHITECTURE.md, DEPLOYMENT.md, MONITORING.md и API_REFERENCE.md
  - Упрощена структура: удалены устаревшие разделы про нативный запуск и автоматический запуск (оставлены только в разделе устранения неполадок)
  - Добавлены полезные команды для работы с Docker Compose и раздел устранения неполадок
  - Документ теперь служит быстрым стартом для новых разработчиков, желающих запустить проект локально
- **Главный README** (`README.md`): полностью переработан и превращён в главную точку входа и навигационный центр для всей документации проекта
  - Добавлена визуальная секция с логотипом проекта и badges (CI Status, License, Codecov)
  - Обновлено краткое описание с актуальной ссылкой на Telegram-бота (@wednesday_morning_bot)
  - Реорганизована структура документа для лучшей навигации:
    - Ключевые возможности представлены в виде таблицы по категориям и детального маркированного списка
    - Добавлена секция "Начало работы" с быстрым стартом и ссылкой на INSTALLATION.md
    - Создан навигационный центр документации с таблицами ссылок на все документы:
      - Для разработчиков: ARCHITECTURE.md, INSTALLATION.md, PROJECT_SUMMARY.md
      - Для операторов/админов: DEPLOYMENT.md, MONITORING.md
      - Справочник: API_REFERENCE.md
      - Дополнительные материалы (CHANGELOG, release notes, SQL)
  - Сохранена вся важная техническая информация (команды, структура проекта, конфигурация, Celery, системные особенности)
  - Добавлены ссылки на соответствующие документы в ключевых разделах для улучшения навигации
  - Улучшена визуальная структура с использованием эмодзи и таблиц для лучшей читаемости
  - README теперь служит единой отправной точкой для пользователей, разработчиков и администраторов проекта
  - **Навигация в README.md**: добавлены ссылки на `TYPING_GUIDE.md` и `TESTING_GUIDE.md` в раздел для разработчиков, а также ссылка на `LOKI_PROMTAIL_SCHEMA.md` в раздел для операторов и администраторов
  - **API_REFERENCE.md**: добавлено примечание о том, что команда `/frog` выполняется синхронно в обработчике бота и не использует Celery для фоновой обработки, в отличие от автоматических отправок по расписанию (уточнение добавлено также в `ARCHITECTURE.md` для полноты документации)
  - **ARCHITECTURE.md**:
    - обновлён раздел Healthcheck с упоминанием проверки доступности очереди метрик `metrics:events` (Redis Stream) и проверки доступности Celery workers/Heartbeat для Celery Beat
    - Добавлена новая Sequence Diagram (Диаграмма 2a) для визуализации синхронного потока команды `/frog` без использования Celery, наглядно показывающая разницу с асинхронным потоком автоматических отправок
    - Добавлена детальная Sequence Diagram (Диаграмма 3a) для визуализации полного потока автоматической отправки через Celery, включая lazy инициализацию сервисов, взаимодействие с Redis и PostgreSQL, обработку ошибок и retry логику
    - Добавлено примечание в раздел "Потоки данных" о том, что команда `/frog` выполняется синхронно в обработчике бота и не использует Celery для фоновой обработки, что обеспечивает быстрый ответ пользователю
  - **LOKI_PROMTAIL_SCHEMA.md**:
    - Добавлен новый раздел "Типичные сценарии отладки" с практическими примерами LogQL-запросов для диагностики проблем:
      - Анализ производительности генераций (топ-10 самых медленных)
      - Поиск всех ошибок за последний час с группировкой по типу
      - Корреляция событий по `user_id` и `task_id`
      - Мониторинг Circuit Breaker срабатываний
      - Диагностика проблем с генерацией изображений
      - Отслеживание проблем с Celery задачами
      - Анализ rate limiting
    - Расширены примеры LogQL-запросов для различных сценариев поиска и анализа логов
  - **MONITORING.md**: упрощён раздел об архитектуре интеграции, добавлена ссылка на `ARCHITECTURE.md` для получения подробной информации о работе Celery, что устраняет дублирование технических деталей
  - **README.md**: добавлен раздел "🚀 Быстрые ссылки" сразу после краткого описания для быстрого доступа к ключевым документам (установка, развертывание, справочник команд, архитектура)
  - **TYPING_GUIDE.md**: добавлены примеры типизации сложных Celery задач:
    - Задачи с `*args` и `**kwargs`
    - Задачи с callback'ами
    - Задачи с retry логикой и автоматическим retry через `autoretry_for`
    - Задачи с сигналами Celery (`task_prerun`, `task_postrun`)
  - **INSTALLATION.md**: расширен раздел "Устранение неполадок" с дополнительными сценариями:
    - Проблемы с правами доступа к secrets (проверка прав, изменение владельца)
    - Проблемы с сетью между контейнерами (проверка доступности, настройки сети)
    - Проблемы с миграциями при обновлении (проверка схемы, пересоздание БД)
    - Проблемы с Celery worker при первом запуске (проверка Redis, переменных окружения)

### Изменено

- **Унификация команд миграций базы данных**:
  - В `docs/INSTALLATION.md` и `docs/DEPLOYMENT.md` все упоминания команд миграции (например, `docker compose run --rm bot python3 -m utils.postgres_schema`) заменены на унифицированную команду `make migrate`
  - Это упрощает процесс миграции и обеспечивает единообразие инструкций во всей документации
  - Обновлены все разделы, связанные с миграциями: первый запуск, обновление бота, troubleshooting
- **Консистентность команд Docker Compose**:
  - В `docs/INSTALLATION.md` команда запуска обновлена для явного указания файла `docker-compose.yml` (`docker compose -f docker-compose.yml up -d --build`) для консистентности с `docs/DEPLOYMENT.md`
  - Это устраняет возможную путаницу при использовании разных файлов docker-compose
- **Упрощение раздела миграций в DEPLOYMENT.md**:
  - Альтернативный способ выполнения миграций через docker-compose перемещён в collapsible блок "Альтернативный способ (не рекомендуется)"
  - Основным способом остаётся унифицированная команда `make migrate`, что упрощает навигацию и снижает вероятность ошибок

### Исправлено

- **Типизация в `bot/handlers.py`**:
  - Добавлен `from __future__ import annotations` в начало файла для поддержки современного синтаксиса типизации Python 3.10+
- **Типизация в `services/image_generator.py`**:
  - Заменён `Optional["Metrics"]` на современный синтаксис `"Metrics" | None` в параметре `metrics` метода `generate_frog_image()`
  - Удалён неиспользуемый импорт `Optional` из `typing`
  - Изменения соответствуют рекомендациям из `TYPING_GUIDE.md` по использованию оператора `|` вместо `Optional` и `Union`

---

## [6.7.13] 2025-12-12 — Рефакторинг CI/CD: унификация тестов и переиспользование workflows

### Добавлено

- **Унифицированный Pytest workflow** (`.github/workflows/jobs/pytest_full.yml`):
  - Объединены все Pytest-тесты (unit, integration, e2e, e2e-infra, slow, celery) в единый переиспользуемый workflow job
  - Реализован единый жизненный цикл Docker контейнеров: Start Containers → All Tests → Stop Containers
  - Условный запуск `test-slow` и `test-celery` только при релизах (`is_release == true`)
  - Автоматический сбор всех файлов покрытия (`.coverage.*`) и JUnit отчётов (`junit-*.xml`) в единые артефакты
- **Reusable workflows для проверок**:
  - `.github/workflows/jobs/prometheus-check.yml` — проверка конфигурации Prometheus и правил
  - `.github/workflows/jobs/loki-dashboards-check.yml` — валидация JSON дашбордов Loki
- **Job для определения типа запуска** (`check_release`):
  - Определяет, является ли запуск релизом (тег `v*`)
  - Используется для условного запуска тестов и сборки Docker образа

### Изменено

- **Структура CI pipeline** (`.github/workflows/ci.yml`):
  - Все reusable workflows перенесены в директорию `jobs/` для единообразия
  - Удалены отдельные jobs для тестов (`test-unit`, `test-integration`, `test-e2e`, `test-e2e-infra`, `test-slow`, `test-celery`)
  - Все тесты объединены в единый job `pytest-full` для переиспользования Docker контейнеров
  - Упрощены jobs объединения результатов: `coverage-merge` и `junit-merge` работают с едиными артефактами от `pytest-full`
  - `docker-build` использует логику `check_release` вместо прямого условия `startsWith(github.ref, 'refs/tags/v')`
- **Упрощённые workflows объединения**:
  - `.github/workflows/jobs/coverage_merge.yml` — скачивает и обрабатывает только один артефакт `coverage-all`
  - `.github/workflows/jobs/junit_merge.yml` — скачивает и обрабатывает только один артефакт `junit-all`
- **Обновлены пути к reusable workflows**:
  - `lint`, `format`, `mypy` — обновлены пути на `./.github/workflows/jobs/*.yml`
  - `prometheus`, `loki-dashboards` — переведены на reusable workflows
  - `docker-build` — обновлён путь и использует логику `check_release`

### Улучшено

- Переиспользование Docker контейнеров: контейнеры запускаются один раз и переиспользуются всеми тестами, что ускоряет выполнение CI
- Упрощённая структура зависимостей: `coverage-merge` и `junit-merge` зависят только от `pytest-full`
- Единообразная структура: все reusable workflows находятся в директории `jobs/`

---

## [6.7.12] 2025-12-11 — Надёжность тестовой среды и покрытий

### Изменено

- `tests/docker-compose.test.yml`: ускорён healthcheck Redis (2s/3s/10, `redis-cli --raw ping`), сервис `tests` запускает pytest по умолчанию (не наследует Celery CMD), добавлены безопасные дефолты для тестовых токенов/ID (dummy), `POSTGRES_PASSWORD` оставлен обязательным.
- `tests/conftest.py`: автоконфиг больше не перезаписывает переменные окружения, если они уже заданы (compose/CI/.env.test), что убирает конфликты с паролями БД; обновлён тестовый пароль по умолчанию.
- `Makefile`: перед `coverage combine` пути в всех `.coverage.*` нормализуются через `scripts/fix_coverage_paths.py`, устраняя предупреждения coverage о путях `/app/...`.

---

## [6.7.11] 2025-12-11 — Усиление безопасности docker-compose и secrets

### Добавлено

- Поддержка *_FILE секретов в `utils/config.py` для чтения паролей из Docker secrets.
- Документ `docs/docker-compose-refactor.md` с описанием изменений и примерами конфигурации.
- Примерные секреты для prod-compose по умолчанию в `./secrets` (postgres/redis/grafana) для локальных прогонов.

### Изменено

- Продакшн `docker-compose.yml`: вынесены пароли Postgres/Redis/Grafana в Docker secrets, сегментация сетей `backend/monitoring`, закрыты публичные порты (кроме Grafana на 127.0.0.1), добавлены ресурсные лимиты и ротация логов json-file, исправлен healthcheck бота с `${HEALTHCHECK_PORT}`, Prometheus ждёт здоровые зависимости.
- CI `tests/docker-compose.test.yml`: убраны публикации портов Postgres/Redis (только internal `expose`), удалены жёсткие дефолты секретов/токенов (ожидаются из CI env), добавлены ресурсные лимиты и ротация логов, сохранён tmpfs для быстрого IO.

---

## [6.7.10] 2025-12-11 — Усиление алертинга по логам и проверок Loki

### Добавлено

- CI-задача `loki-dashboards`: валидация JSON дашборда логов для раннего обнаружения поломок панелей/provisioning.

### Изменено

- Алерты по логам (Grafana UA): добавлены метки `severity` и runbook-аннотации для high-error-rate и suspicious-secrets.

---

## [6.7.9] 2025-12-11 — Интеграция мониторинга Prometheus/Grafana и дашборды метрик

### Добавлено

- Prometheus в docker-compose: хранение в `prometheus_data`, retention 15d, hot-reload и healthcheck.
- Конфиг Prometheus с scrape `/metrics` для bot/celery-worker/celery-beat, правила recording/alerting и promtool unit-тесты.
- Grafana provisioning: datasource `prom_ds`, unified alerting по метрикам, дашборды (app, celery, retry) как code.
- CI job `prometheus`: установка promtool 2.54.1, `promtool check config` и `promtool test rules`.

### Изменено

- Datasource Loki перестал быть default, чтобы Prometheus был источником по умолчанию для метрик.
- Провайдер дашбордов Grafana унифицирован под метрики и логи (dashboards-as-code).

---

## [6.7.8] 2025-12-10 — Рефакторинг тестового пайплайна: детерминированный жизненный цикл контейнеров и оптимизация фикстур

### Добавлено

- **Детерминированный тестовый пайплайн**:
  - Реализован единый жизненный цикл контейнеров: запуск один раз → переиспользование → остановка один раз
  - Добавлена идемпотентность в `scripts/test_up.sh`: проверка состояния контейнеров перед запуском
  - Добавлены healthchecks для ожидания готовности Postgres, Redis и Celery worker
  - Раздельное покрытие кода для каждой фазы тестов: `.coverage.unit`, `.coverage.integration`, `.coverage.e2e`, `.coverage.infra`
  - Новый target `coverage-merge` для объединения покрытия из всех фаз в `coverage.xml`
  - Поддержка параллельного запуска тестов через `TEST_XDIST` (xdist), по умолчанию включена (`TEST_XDIST=1`)
- **Диагностика и вспомогательные скрипты**:
  - `scripts/fix_coverage_paths.py` — исправляет пути `/app/...` в coverage, полученных из Docker, на локальные (все сообщения на русском языке)
  - Диагностический дамп pending asyncio задач в session `event_loop` с автоотменой перед закрытием loop
- **Pytest-скрипты по типам тестов**: `scripts/pytest_unit.sh`, `scripts/pytest_integration.sh`, `scripts/pytest_e2e.sh`, `scripts/pytest_infra.sh` — принимают `MARK_EXPR/COVERAGE_FILE/JUNIT_FILE/PYTEST_XDIST`, не содержат Docker-логики, устанавливают `PYTHONPATH` для корректных импортов.
- Шим для миграций в контейнере: `tests/utils/postgres_schema.py` (использует основной код `utils.postgres_schema`).
- **Автоматическая установка PYTHONPATH**: в `tests/conftest.py` добавлена установка корня проекта в `sys.path` до всех импортов для корректной работы unit-тестов локально.

- **Улучшенная обработка ошибок в тестах**:
  - Добавлена функция `_is_running_in_ci()` для определения CI окружения через `GITHUB_ACTIONS` и `CI`
  - Добавлена функция `_handle_postgres_error()`: в CI вызывает `pytest.fail()`, локально — `pytest.skip()`
  - Улучшена обработка ошибок подключения к PostgreSQL с учётом окружения
- **Фикстуры для управления ресурсами**:
  - Добавлена фикстура `gigachat_client` в `tests/conftest.py` для автоматического закрытия `aiohttp.ClientSession` после тестов
  - Фикстура создаёт `GigaChatTextClient` с параметрами по умолчанию и автоматически вызывает `aclose()` в `finally`
- **Объединение отчётов тестирования**:
  - Добавлен target `junit-merge` для объединения всех JUnit XML файлов (`junit-*.xml`) в единый `junit.xml`
  - Реализован скрипт `scripts/merge_junit.py` с использованием `junitparser` для корректного объединения отчётов
  - `junit-merge` интегрирован в `ci` и `ci-full` пайплайны
- **Отдельные таргеты для специфичных тестов**:
  - Добавлен target `test-slow` для запуска долгих тестов (маркер `slow`) в контейнере `tests`
  - Добавлен target `test-celery` для запуска Celery-специфичных тестов (маркер `celery`) в контейнере `tests`
  - Созданы соответствующие скрипты: `scripts/pytest_slow.sh` и `scripts/pytest_celery.sh`

### Изменено

- **Архитектура тестового пайплайна (Makefile)**:
  - Полностью переписан Makefile с новой структурой: `test-unit`, `test-integration`, `test-e2e`, `test-e2e-infra`, `test-slow`, `test-celery`
  - Unit тесты запускаются локально без контейнеров, генерируют `junit-unit.xml`
  - Integration тесты запускаются в контейнере `tests`, используют сервисы Postgres/Redis из `test-up`
  - E2E тесты запускаются внутри `docker compose run tests`, переиспользуют уже запущенные контейнеры
  - Slow и Celery тесты запускаются в контейнере `tests` с отдельными coverage файлами (`.coverage.slow`, `.coverage.celery`)
  - CI target переработан: контейнеры запускаются один раз и переиспользуются всеми тестами
  - Добавлен target `ci-full` для запуска всех тестов (включая slow и celery), `ci` запускает только быстрые тесты (209 из 231)
  - DRY переменные для pytest (`COV_ARGS`, `COV_REPORT`, `COV_FAIL_UNDER`) и docker compose (`COMPOSE_PROJECT`, `COMPOSE_FILE`, `COMPOSE_TEST`)
- Тестовая инфраструктура перенесена в `tests/`: `tests/docker-compose.test.yml`, `tests/Dockerfile.test`, `tests/.env.test`; `test-up`/`test-down` используют единый `COMPOSE_TEST/COMPOSE_CMD`.
- **Переменные окружения вынесены в `tests/.env.test`**: все тестовые переменные (Postgres, Redis, токены, настройки) теперь в одном месте, `docker-compose.test.yml` использует подстановки `${VAR:-default}`.
- `TEST_XDIST` по умолчанию включён (`=1`), `PYTEST_XDIST` прокидывается во все pytest-запуски (unit/integration/e2e/infra).
- `migrate` выполняется в контейнере `tests` через `tests.utils.postgres_schema`, использует переменные окружения из `docker-compose.test.yml` (не перезаписывает `POSTGRES_HOST=postgres_test`).
- `coverage-merge` стал устойчивее: использует `$(wildcard .coverage.*)` и не падает при отсутствии части фаз.

- **Скрипты управления контейнерами**:
  - `scripts/test_up.sh`: добавлена идемпотентность, healthchecks, использование явного project name (`wednesday_test`)
  - `scripts/test_down.sh`: остановка только тестового проекта, не затрагивает другие локальные контейнеры
  - Использование `--env-file tests/.env.test` для переменных окружения вместо shell `export`

- **Архитектура фикстур PostgreSQL**:
  - Вернут `async_postgres_pool` на `scope="session"` — пул создаётся один раз на сессию и переиспользуется всеми тестами
  - Обновлён `_setup_test_postgres` на `scope="session"` для соответствия новому scope пула
  - `cleanup_tables` теперь использует `TRUNCATE ... RESTART IDENTITY CASCADE` и инициализирует схему при её отсутствии
  - `postgres_transaction` оставлен для быстрых тестов, очистка таблиц вынесена в `cleanup_tables`
  - Введена session-фикстура `event_loop` с диагностикой pending задач и принудительной отменой перед закрытием loop
  - В `pyproject.toml` задано `asyncio_default_*_loop_scope = "session"` для единообразного event loop в асинхронных тестах

### Исправлено

- **Определение окружения в тестах**:
  - Убрано использование `TESTING="1"` для определения окружения — теперь используется только `/.dockerenv`
  - Улучшена логика определения Docker окружения через `_is_running_in_docker()`
- **Изоляция и схемы БД**:
  - Исправлены падения `UndefinedTableError` в tests/test_utils/* (prompts/images/metrics) — схема создаётся в `async_postgres_pool`, `cleanup_tables` пересоздаёт при необходимости
  - Тест `test_admins_store_add_admin_duplicate` изолирован через `cleanup_tables` вместо транзакции
- **Покрытие кода**:
  - Устранена ошибка `No source for code: /app/...` — пути coverage из Docker переписываются на локальные через `scripts/fix_coverage_paths.py`
  - `coverage combine` больше не падает при отсутствии отдельных файлов покрытия, даёт понятные предупреждения
  - Добавлена попытка финализации SQLite coverage через `coverage xml -o /dev/null` в скриптах pytest для улучшения синхронизации через Docker volume (вывод в `/dev/null` для финализации без создания лишних файлов)
- **Импорты в unit-тестах**:
  - Исправлена ошибка `ModuleNotFoundError: No module named 'utils.config_test'` в unit-тестах через установку `PYTHONPATH` в `pytest_unit.sh` и `sys.path` в `conftest.py`
- **Управление ресурсами в тестах**:
  - Исправлено предупреждение "Unclosed client session" для `GigaChatTextClient` — все тесты, создающие клиент вручную, теперь явно закрывают его через `await client.aclose()` в `finally` блоке
  - Обновлены тесты в `tests/test_services/test_gigachat_text_client.py` и `tests/test_smoke_low_coverage.py` для корректного закрытия клиентов

### Улучшено

- **Производительность тестов**:
  - Контейнеры запускаются один раз и переиспользуются всеми фазами тестирования (unit, integration, e2e, e2e-infra)
  - Пул PostgreSQL создаётся один раз на сессию вместо создания для каждого теста
  - Убрана избыточная очистка таблиц — используется только транзакционный rollback

- **Надёжность и воспроизводимость**:
  - Детерминированный пайплайн: одинаковое поведение в локальном окружении и CI
  - Идемпотентность `test-up`: безопасный повторный запуск без перезапуска уже работающих контейнеров
  - Изоляция тестовых контейнеров через явный project name (`wednesday_test`)
  - Раздельное покрытие кода позволяет анализировать покрытие по фазам тестирования

- **Удобство разработки**:
  - `TEST_XDIST` по умолчанию включён (`=1`) для ускорения всех типов тестов через параллельный запуск (xdist)
  - Улучшенные сообщения об ошибках с учётом окружения (CI vs локальное)
  - Опциональная очистка временных файлов через target `clean`
  - Объединение JUnit XML отчётов в единый файл для удобного анализа результатов CI
  - Разделение быстрых и полных прогонов: `make ci` (209 тестов) и `make ci-full` (231 тест, включая slow и celery)

---

## [6.7.7] 2025-12-10 — Исправление архитектуры тестов: подключение к PostgreSQL и event loops

### Исправлено

- **Подключение к PostgreSQL в тестах**:
  - Исправлена логика определения окружения (Docker vs локальное) в `tests/conftest.py`
  - Добавлена функция `_is_running_in_docker()` для автоматического определения окружения через `/.dockerenv` и переменную `TESTING="1"`
  - `POSTGRES_HOST` теперь устанавливается условно: в Docker контейнере — `postgres_test`, локально — `localhost`
  - Переменные окружения из `docker-compose.test.yml` больше не перезаписываются принудительно
  - Все integration тесты с `@pytest.mark.db` теперь корректно подключаются к PostgreSQL

- **Проблемы с event loops в pytest-asyncio**:
  - Исправлена ошибка "RuntimeError: got Future attached to a different loop" в async-фикстурах
  - Изменён scope `async_postgres_pool` с `session` на `function` для создания пула в том же event loop, что и тесты
  - Изменён scope `_setup_test_postgres` с `session` на `function` для соответствия новому scope пула
  - Добавлена фикстура `event_loop` с `scope="session"` для единого event loop во всех async-тестах
  - Исправлена фикстура `postgres_transaction`: патчит `get_postgres_pool()` вместо `pool.acquire()` (read-only атрибут)
  - Добавлена очистка таблиц в `postgres_transaction` перед началом транзакции для изоляции тестов

- **Обработка ошибок подключения к PostgreSQL**:
  - Улучшены сообщения об ошибках подключения с указанием окружения (Docker vs локальное)
  - Тесты пропускаются с `pytest.skip()` вместо падения с неясными ошибками
  - Добавлены понятные подсказки: "Запустите `make test-up` для поднятия тестовых контейнеров"

### Изменено

- **Архитектура фикстур PostgreSQL**:
  - `async_postgres_pool` теперь создаёт пул для каждого теста (function scope) вместо одного на сессию
  - `_ensure_postgres_schema` использует переданный пул напрямую для инициализации схемы, избегая проблем с event loops
  - `cleanup_tables` и `postgres_transaction` используют `get_postgres_pool()` напрямую без вызова `_ensure_postgres_schema`
  - `postgres_transaction` теперь очищает таблицы перед началом транзакции для гарантии изоляции тестов

### Улучшено

- **Документация тестов**:
  - Добавлен раздел "Конфигурация подключения к PostgreSQL" в `tests/README.md`
  - Описана логика определения окружения и установки `POSTGRES_HOST`
  - Добавлены примеры правильного использования фикстур для работы с PostgreSQL

- **Надёжность тестов**:
  - Все integration тесты с PostgreSQL теперь работают стабильно без ошибок event loops
  - Улучшена изоляция тестов: каждый тест начинается с чистой БД
  - Упрощена логика фикстур для лучшей поддерживаемости

---

## [6.7.6] 2025-12-10 — Оптимизация Docker-конфигурации для production: read_only, tmpfs, минимизация образа

### Добавлено

- **E2E тесты для volumes**:
  - Создан `scripts/test_volumes.sh` для проверки корректности монтирования volumes в Docker контейнерах
  - Проверка доступности volumes (`/app/data/frogs`, `/app/data/prompts`) в bot и celery-worker
  - Проверка записи в volumes и изоляции между контейнерами
  - Проверка отсутствия `/app/logs` (логи только в stdout)
  - Проверка доступности `/tmp` для записи (tmpfs)

- **CI проверки Docker образа**:
  - Добавлена проверка отсутствия runtime-данных в образе (`.dockerignore` работает корректно)
  - Проверка работы контейнера с `read_only: true` и tmpfs
  - Проверка установки `PYTHONDONTWRITEBYTECODE=1` в образе
  - Проверка отсутствия `/app/logs` в образе

### Изменено

- **Оптимизация Dockerfile для production**:
  - Удалена директория `/app/logs` из образа (логи только в stdout, Promtail читает Docker logs)
  - Оптимизирован порядок COPY: entrypoint скопирован раньше для лучшего кэширования слоёв
  - Добавлены переменные окружения `PYTHONDONTWRITEBYTECODE=1` и `PYTHONUNBUFFERED=1` для предотвращения создания Python кешей
  - Создаются только необходимые директории для volumes: `/app/data/prompts`, `/app/data/beat`, `/app/data/frogs`

- **Обновление docker-compose.yml для безопасности**:
  - Добавлен `read_only: true` для всех сервисов (`bot`, `celery-worker`, `celery-beat`)
  - Добавлены tmpfs для всех путей записи: `/tmp`, `/var/tmp`, `/root/.cache`, `/run`, `/celerybeat-schedule`
  - Добавлен `PYTHONDONTWRITEBYTECODE=1` в environment всех сервисов
  - Обновлён `bot-init`: удалён volume `logs`, синхронизированы volumes с основными сервисами

- **Расширение .dockerignore**:
  - Добавлены runtime-файлы: `*.jsonl`, `*.tmp`
  - Добавлены coverage файлы: `coverage.*`, `junit-e2e.xml`, `junit-e2e-infra.xml`
  - Предотвращает попадание runtime-данных и тестовых артефактов в Docker образ

- **Оптимизация работы с временными файлами**:
  - Изменён `utils/images_store.py` для использования `/tmp` вместо директории с финальным файлом
  - Временные файлы создаются через `tempfile.NamedTemporaryFile` в `/tmp` для совместимости с `read_only: true`

### Улучшено

- **Безопасность контейнеров**: все сервисы работают в режиме `read_only: true` с минимальными правами записи только в tmpfs
- **Размер образа**: исключены runtime-данные, логи и тестовые артефакты из образа
- **Логирование**: логи пишутся только в stdout (best-practice для Promtail/Loki), не требуют volume для логов
- **Производительность**: оптимизирован порядок слоёв в Dockerfile для лучшего кэширования

---

## [6.7.5] 2025-12-09 — Документация и контроль качества тестов: расширение документации и автоматические проверки

### Добавлено

- **Расширенная документация по тестированию**:
  - Обновлён `tests/README.md` с детальными правилами использования маркеров:
    - Раздел "Правила использования маркеров" с примерами правильной и неправильной маркировки для `unit`, `integration`, `e2e`, `infra`
    - Описание ресурсных маркеров (`db`, `redis`, `celery`, `slow`) с примерами использования
    - Примеры комбинаций маркеров и антипаттернов
  - Добавлены примеры команд для каждого таргета с ожидаемым выводом:
    - `make test-unit-no-container` — unit-тесты без контейнеров
    - `make test-integration-containers` — integration-тесты с контейнерами
    - `make test-integration-containers-xdist` — integration-тесты с параллельным запуском
    - `make test-e2e` — E2E тесты без infra
    - `make test-e2e-infra` — инфраструктурные E2E тесты
  - Расширена документация о coverage threshold:
    - Объяснение концепции и назначения
    - Текущий порог (50%) и где он используется
    - Описание поведения при падении ниже порога
    - Рекомендации по исправлению
  - Добавлено описание фикстур (autouse vs opt-in):
    - Список autouse фикстур (`session_env_defaults`, `base_env`, `patch_models_store`) с описанием
    - Список opt-in фикстур (`cleanup_tables`, `postgres_transaction`, `celery_test_queues`, `reset_singletons`) с примерами использования
    - Правила выбора между autouse и opt-in
    - Примеры правильного и неправильного использования

- **Детальное руководство по написанию тестов**:
  - Создан `docs/testing_guidelines.md` с полным руководством:
    - Раздел "Маркеры тестов" с детальными правилами для каждого типа маркера
    - Раздел "Фикстуры: autouse vs opt-in" с правилами создания и использования
    - Раздел "Правила написания тестов" для unit/integration/e2e тестов
    - Раздел "CI/Pre-commit проверки" с описанием автоматических проверок и способами исправления ошибок
    - Примеры правильного и неправильного кода для каждого случая

- **Скрипт автоматической проверки качества тестов**:
  - Создан `tests/check_test_quality.py` для проверки соответствия тестов правилам:
    - Проверка запрета новых autouse фикстур (кроме разрешённых: `session_env_defaults`, `base_env`, `patch_models_store`)
    - Проверка наличия маркеров ресурсов (`db`, `redis`, `celery`, `slow`) где необходимо
    - Проверка соответствия маркеров использованным фикстурам
    - Поддержка `pytestmark` на уровне модуля
    - Понятные сообщения об ошибках и предупреждениях с указанием файла и строки

- **Интеграция проверок качества в CI/CD**:
  - Добавлен локальный hook `check-test-quality` в `.pre-commit-config.yaml`:
    - Запускается автоматически на pre-commit
    - Предотвращает коммит неправильно размеченных тестов
  - Добавлен job `test-quality-check` в `.github/workflows/pytest-check.yml`:
    - Запускается в CI для всех pull requests
    - Блокирует merge при обнаружении ошибок в размеченных тестах

### Изменено

- **Улучшена документация транзакционного rollback vs TRUNCATE**:
  - Обновлён раздел "Изоляция тестов с PostgreSQL" в `tests/README.md`
  - Добавлены детальные примеры использования обеих фикстур
  - Уточнены рекомендации по выбору подхода

---

## [6.7.4] 2025-12-09 — Улучшение стабильности Celery-тестов: изоляция очередей, снижение таймаутов и retry/backoff

### Добавлено

- **Изоляция тестовых очередей Celery через динамические имена**:
  - Обновлена функция `generate_celery_test_queues()` в `tests/common/celery_app_test.py` для генерации уникальных имён очередей через UUID
  - Каждый тест получает уникальный набор очередей (`test_main_{uuid}`, `test_images_{uuid}`, `test_maintenance_{uuid}`)
  - Worker подписывается на динамические очереди через control API (`ensure_queues_consumed()`) без перезапуска
  - Очереди автоматически отписываются после теста через `drop_test_consumers()` для предотвращения засорения worker
  - Исключены конфликты между параллельными тестами при использовании одинаковых имён очередей

- **Троттлинг долгих задач в тестовом Celery app**:
  - Добавлены ограничения времени выполнения задач в `tests/common/celery_app_test.py`:
    - `task_time_limit = 30` секунд (жесткий лимит)
    - `task_soft_time_limit = 25` секунд (мягкий лимит)
  - Предотвращает зависания тестов при добавлении долгих задач в будущем

- **Retry/backoff вместо skip при недоступности worker**:
  - Обновлена функция `wait_for_celery_worker()` в `tests/common/wait_for_celery.py`:
    - Улучшен экспоненциальный backoff (multiplier=1.0, min=0.5, max=5.0)
    - Снижен таймаут `result.get()` до 5 секунд для быстрого обнаружения проблем
  - Добавлена функция `_get_worker_stats_with_retry()` в `tests/test_services/test_celery_e2e.py` с retry/backoff вместо `pytest.skip()` при недоступности worker

### Изменено

- **Снижение таймаутов в Celery-тестах**:
  - Все вызовы `result.get()` в Celery-тестах используют таймаут 5 секунд (вместо 10)
  - Ускорено обнаружение проблем и уменьшено время выполнения тестов
  - Обновлены тесты в `tests/e2e/celery/test_celery_e2e_basic.py` и `tests/test_services/test_celery_e2e.py`

- **Обновление тестов для использования динамических очередей**:
  - Все тесты в `tests/e2e/celery/test_celery_e2e_basic.py` используют фикстуру `celery_test_queues` для получения динамических очередей
  - Все тесты в `tests/test_services/test_celery_e2e.py`, работающие с очередями, обновлены для использования динамических очередей:
    - `test_celery_task_can_be_sent_to_queue`
    - `test_celery_task_routing`
    - `test_celery_task_result_backend`
    - `test_celery_multiple_workers_concurrency`
    - `test_celery_task_retry_mechanism`
  - Тесты полностью изолированы друг от друга и могут безопасно выполняться параллельно

---

## [6.7.3] 2025-12-09 — Расширение smoke-тестов для модулей с низким покрытием

### Добавлено

- **Расширение smoke-тестов для low-coverage модулей**:
  - Добавлены smoke-тесты для 8 модулей в `tests/test_smoke_low_coverage.py`:
    - `services/clients/kandinsky.py` — тесты инициализации клиента и формирования заголовков авторизации
    - `services/clients/gigachat_text.py` — тест инициализации клиента с моками aiohttp
    - `utils/admins_store.py` — тесты методов `is_admin` и `list_admins` с моками Postgres
    - `utils/models_store.py` — тесты get/set моделей Kandinsky и GigaChat с моками Postgres
    - `utils/dispatch_registry.py` — тесты проверки и пометки отправки сообщений с моками Postgres
    - `utils/usage_tracker.py` — тесты инкремента и получения месячного тотала с моками Postgres
    - `utils/chats_store.py` — тесты добавления чатов и получения списка чатов с моками Postgres
    - `utils/metrics.py` — тесты инкремента метрик и получения сводки с моками Postgres
  - Все тесты являются unit-тестами (без контейнеров, с моками БД/Redis/API)
  - Все тесты помечены маркером `@pytest.mark.unit` для запуска через `make test-unit-no-container`
  - Используются моки Postgres через `monkeypatch` с корректной эмуляцией async context manager для `pool.acquire()`

- **Исправление предупреждений pytest**:
  - Переименована функция `test_ping` в `ping_task` в `tests/common/celery_tasks_test.py`
  - Обновлён импорт в `tests/common/celery_app_test.py`
  - Устранены предупреждения `PytestReturnNotNoneWarning` для Celery задач

---

## [6.7.2] 2025-12-09 — Оптимизация производительности тестов: параллельный запуск с xdist, транзакционный rollback и session-пул

### Добавлено

- **Параллельный запуск integration-тестов с pytest-xdist**:
  - Добавлен `pytest-xdist==3.6.1` в `requirements.txt` и `pyproject.toml`
  - Добавлен таргет `make test-integration-containers-xdist` для запуска integration-тестов с параллельным выполнением (`-n auto`)
  - Тесты с маркерами `slow`, `celery`, `e2e`, `infra` автоматически исключаются из параллельного запуска для предотвращения конфликтов

- **Фикстура для транзакционного rollback**:
  - Создана фикстура `postgres_transaction` в `tests/conftest.py` (scope="function", opt-in)
  - Фикстура создаёт транзакцию (BEGIN) перед тестом и выполняет ROLLBACK после теста
  - Быстрее, чем TRUNCATE, но не подходит для тестов, которые проверяют commit'ы в БД
  - Патчит `pool.acquire()` для использования одной транзакции во всех операциях теста
  - Обновлены тесты в `test_chats_store.py` и `test_admins_store.py` для использования новой фикстуры

- **Session-фикстура для async pool**:
  - Создана session-фикстура `async_postgres_pool` в `tests/conftest.py` (scope="session")
  - Фикстура создаёт пул соединений один раз на сессию с минимальными параметрами (min_size=1, max_size=2)
  - Корректно закрывает пул после всех тестов через `close_postgres_pool()`
  - Каждый worker в xdist имеет свой собственный пул для предотвращения конфликтов
  - Обновлён `_setup_test_postgres` для использования session-пула
  - Обновлены `cleanup_tables` и `postgres_transaction` для автоматического использования session-пула, если он доступен

### Изменено

- **Документация тестов**:
  - Добавлен раздел "Изоляция тестов с PostgreSQL" в `tests/README.md`
  - Документированы два подхода к изоляции: `cleanup_tables` (TRUNCATE) и `postgres_transaction` (ROLLBACK)
  - Описаны преимущества и недостатки каждого подхода с рекомендациями по использованию
  - Добавлены примеры использования обеих фикстур

---

## [6.7.1] 2025-12-09 — Доработка инфраструктуры тестирования: coverage threshold, переразметка тестов и фикстура reset синглтонов

### Добавлено

- **Coverage threshold для тестов**:
  - Добавлен `--cov-fail-under=50` в CI workflow для unit и integration jobs
  - Добавлен `--cov-fail-under=50` в Makefile для таргетов `test-integration-containers` и `ci`
  - Тесты завершаются с ошибкой, если покрытие кода ниже 50%
  - Документирован порог покрытия в `tests/README.md`

- **Фикстура для сброса синглтонов**:
  - Создана фикстура `reset_singletons` в `tests/conftest.py` (scope="function", opt-in)
  - Фикстура автоматически сбрасывает состояние `CeleryServices` (_bot, _generator, _initialized) перед тестом
  - Восстанавливает исходное состояние после теста для обеспечения изоляции
  - Обновлены тесты в `test_celery_tasks.py` для использования фикстуры вместо ручного сброса

### Изменено

- **Переразметка тестов handlers и ботов**:
  - Заменены маркеры `@pytest.mark.e2e` на `@pytest.mark.integration` для тестов, использующих реальные Postgres хранилища
  - Обновлены тесты в `test_handlers.py` (9 тестов) и `test_wednesday_bot.py` (2 теста)
  - Тесты с реальными хранилищами теперь корректно попадают в integration-прогон вместо e2e
  - Улучшена изоляция между unit, integration и e2e тестами

---

## [6.7.0] 2025-12-09 — Улучшение инфраструктуры тестирования: разделение таргетов, CI матрица и smoke-тесты

### Добавлено

- **Разделение таргетов тестов в Makefile**:
  - Добавлен таргет `make test-unit-no-container` для запуска unit-тестов без контейнеров (с моками БД/Redis/Celery)
  - Добавлен таргет `make test-integration-containers` для интеграционных тестов с Postgres/Redis (без Celery e2e)
  - Добавлен таргет `make test-e2e-infra` для Celery infra-тестов с отдельным маркером `infra`
  - Все таргеты корректно фильтруют тесты по маркерам (`unit`, `integration`, `e2e`, `infra`, `slow`, `db`, `redis`, `celery`)

- **Маркировка долгих тестов**:
  - Все тесты в `test_retry.py` помечены маркером `@pytest.mark.slow` через `pytestmark`
  - Тест `test_generate_frog_image_network_error` помечен маркером `@pytest.mark.slow`
  - Маркер `slow` автоматически исключается из быстрых прогонов (unit и integration)

- **Система маркеров pytest**:
  - Определены маркеры в `pyproject.toml`: `unit`, `integration`, `db`, `redis`, `celery`, `e2e`, `infra`, `slow`
  - Все маркеры документированы с описанием назначения
  - Тесты Celery infra (`test_celery_e2e.py`) помечены как `e2e + infra` для отдельного запуска

- **CI матрица для тестов**:
  - Добавлен отдельный job `pytest-unit` для unit-тестов без контейнеров
  - Добавлен отдельный job `pytest-integration` для интеграционных тестов с Postgres/Redis
  - Добавлен отдельный job `pytest-e2e-infra` для Celery infra-тестов
  - Все jobs генерируют JUnit артефакты (`junit-unit.xml`, `junit-integration.xml`, `junit-e2e.xml`)
  - Все jobs генерируют coverage артефакты с флагами (unit, integration, e2e_infra) для раздельного отслеживания покрытия
  - Coverage включён для e2e прогонов для учёта вклада в общее покрытие

- **Smoke-тесты для low-coverage модулей**:
  - Создан файл `tests/test_smoke_low_coverage.py` с базовыми тестами для модулей с низким покрытием
  - Покрыты модули: `services/clients/factory.py`, `services/prompt_cache.py`, `services/rate_limiter.py`, `bot/handlers.py`, `main.py`
  - Все smoke-тесты помечены маркером `@pytest.mark.unit` для запуска без контейнеров

- **Строгий режим pytest-asyncio**:
  - Включён `asyncio_mode = "strict"` в `pyproject.toml` для предотвращения ошибок в async-тестах

### Изменено

- **Оптимизация фикстур pytest**:
  - Фикстура `_setup_test_postgres` сделана opt-in (scope="session") вместо autouse для unit-тестов
  - Фикстура `cleanup_tables` сделана opt-in (scope="function") для точечного использования
  - Фикстура `patch_models_store` остаётся autouse, но автоматически исключает тесты с маркерами `db/integration/e2e/celery/infra`
  - Фикстура `celery_worker_ready` сделана opt-in через `@pytest.mark.usefixtures("celery_worker_ready")` вместо autouse
  - Фикстуры `session_env_defaults` и `base_env` остаются autouse для базовой настройки окружения

- **Документация тестов**:
  - Обновлён `tests/README.md` с описанием матрицы маркеров и команд запуска
  - Добавлена документация по структуре Celery-тестов и разделению на поведенческие и infra-тесты
  - Добавлены примеры команд для каждого таргета

### Исправлено

- **Изоляция тестов**:
  - Улучшена изоляция unit-тестов от внешних зависимостей через автоматическое исключение интеграционных маркеров
  - Устранены конфликты между моками и реальными хранилищами через умную фильтрацию в `patch_models_store`

---

## [6.6.0] 2025-12-09 — Рефакторинг системы логирования: JSON stdout и миграция на docker logs

### Добавлено

- **JSON-логи в stdout по умолчанию**:
  - Основной sink Loguru теперь пишет структурированные JSON-логи в stdout (`serialize=True`)
  - Все Python-сервисы (bot, celery-worker, celery-beat, uvicorn, prometheus) используют единый формат JSON
  - Логи доступны через `docker logs` и автоматически собираются Promtail из docker json-file драйвера
  - Добавлена переменная окружения `LOG_TO_FILE` для опционального включения файловых логов (по умолчанию `0`)
  - При `LOG_TO_FILE=1` создаются два файла: текстовый `wednesday_bot.log` и JSON `wednesday_bot.events.jsonl` для debug/forensics

- **Новые функции логирования**:
  - Добавлена функция `log_http()` для структурированного логирования HTTP-запросов с автоматическим определением статуса
  - Добавлена функция `log_worker()` для логирования Celery-задач с поддержкой task_name, task_id, status и latency_ms
  - Обе функции используют единый API через `log_event()` с маскировкой секретов

- **Интеграция сторонних логеров через LoguruHandler**:
  - Добавлен класс `LoguruHandler` в `utils/logger.py` для интеграции стандартного logging с Loguru
  - Точечная интеграция только `uvicorn` и `prometheus_client` логгеров (без root logger)
  - Все логи от uvicorn и prometheus_client теперь попадают в единый JSON stdout

- **HTTP middleware для логирования запросов**:
  - Добавлен middleware в `services/healthcheck.py` для автоматического логирования всех HTTP-запросов к healthcheck endpoint
  - Логируются метод, путь, статус-код и латентность каждого запроса
  - Uvicorn access_log отключён, логирование выполняется через middleware

- **Heartbeat задача для Celery Beat**:
  - Добавлена периодическая задача `wednesday.beat_heartbeat` (каждые 30 секунд) для создания tmpfs heartbeat файла
  - Задача создаёт/обновляет файл `/tmp/beat-hb` для healthcheck без зависимости от файловых логов

- **Unit тесты для формата логов**:
  - Создан `tests/test_utils/test_logger_format.py` с тестами валидности JSON-структуры логов
  - Тесты проверяют наличие обязательных полей (`timestamp`, `level`, `message`, `extra`)
  - Тесты проверяют, что high-cardinality поля находятся в `extra`, а не на top-level

### Изменено

- **Архитектура логирования**:
  - Минималистичная структура JSON: top-level содержит только `timestamp`, `level`, `message`, `extra`
  - Все метаданные (service, env, event, status, user_id, prompt_hash и др.) находятся в `extra`
  - Это соответствует стандарту Loguru и упрощает Promtail pipeline

- **Маскировка секретов**:
  - Маскировка секретов теперь выполняется только в функциях `log_event()`, `log_http()`, `log_worker()` перед логированием
  - Убраны фильтры на уровне sink'ов для избежания overhead на каждый лог
  - Обычные `logger.info()` без маскировки (для внутренних логов, где секретов нет)

- **Promtail конфигурация**:
  - Promtail теперь читает логи из docker container logs через `/var/lib/docker/containers/*/*-json.log`
  - Упрощён pipeline: `docker` → `json` → `labels` (только service, env, level)
  - High-cardinality поля (event, status, user_id, prompt_hash) остаются в extra, не поднимаются в labels
  - Позиции Promtail перенесены в персистентный volume `promtail_positions:/promtail`

- **Docker Compose конфигурация**:
  - Добавлены переменные окружения `SERVICE_NAME` и `ENV` для всех сервисов (bot, celery-worker, celery-beat)
  - Volume `logs:/app/logs` закомментирован по умолчанию для bot, celery-worker и celery-beat
  - Добавлен volume `promtail_positions` для персистентного хранения позиций Promtail
  - Promtail монтирует `/var/lib/docker/containers` для чтения docker logs

- **Celery Beat конфигурация**:
  - Убран `--logfile=/app/logs/beat.log` из команды запуска beat
  - Beat теперь логирует через LoguruHandler в stdout (JSON)
  - Healthcheck для beat переведён на проверку tmpfs heartbeat файла `/tmp/beat-hb` вместо файла лога

- **Uvicorn конфигурация**:
  - Добавлен параметр `access_log=False` в uvicorn config для отключения встроенного access log
  - Логирование HTTP-запросов выполняется через FastAPI middleware

### Удалено

- **Файловые логи по умолчанию**:
  - Текстовые и JSON файловые логи больше не создаются автоматически
  - Файловые логи доступны только при `LOG_TO_FILE=1` для debug/forensics

### Исправлено

- **Юнит‑тесты логирования**:
  - Обновлены тесты формата логов под актуальную структуру Loguru (`record.extra` и вложенный `extra`)
  - Отключено автоподнятие внешних зависимостей Celery/Postgres в тестах логирования через локальные фикстуры
  - Тесты на маскировку секретов теперь используют `log_event` вместо прямого `logger.bind`, чтобы проверять маскировку в API логирования

---

## [6.5.1] 2025-12-05 — Исправление парсинга JSON-логов в Promtail и синхронизация путей volume

### Исправлено

- **Исправление парсинга JSON-логов loguru в Promtail**:
  - Обновлён `monitoring/promtail-config.yml` для корректной обработки структуры JSON с обёрткой `record`, создаваемой loguru при `serialize=True`
  - Добавлен первый stage `json` для извлечения объекта `record` из корневого JSON
  - Изменено извлечение `level` на `level.name` с сохранением в `level_name` (строка вместо объекта)
  - Изменено использование `time` на `time.repr` для установки timestamp (ISO8601/RFC3339 строка вместо объекта)
  - Обновлена обработка `extra`: pipeline корректно обрабатывает записи без `extra` или без полей `event`/`status`
  - Promtail автоматически пропускает пустые/отсутствующие labels, что предотвращает ошибки парсинга

- **Синхронизация путей volume для promtail**:
  - Изменён volume mount для promtail в `docker-compose.yml`: с `logs:/var/log/wednesday` на `logs:/app/logs` для синхронизации с путём бота
  - Обновлён `__path__` в `promtail-config.yml`: с `/var/log/wednesday/wednesday_bot.events.jsonl` на `/app/logs/wednesday_bot.events.jsonl`
  - Теперь бот и promtail используют одинаковый путь внутри контейнеров, что исключает проблемы с доступом к файлам логов

- **Обновление дашбордов Grafana**:
  - Заменены все использования label `level` на `level_name` в LogQL запросах дашборда `wednesday-logs-dashboard.json`
  - Обновлён алерт "High error rate in logs" в `logging-rules.yml`: заменён `level` на `level_name` в запросе
  - Дашборды теперь корректно отображают данные с новым label `level_name`

- **Обновление документации**:
  - Обновлён `docs/logger_loki_schema.md` с описанием структуры JSON с обёрткой `record`
  - Добавлено описание объектов `level` и `time` с указанием использования `level.name` и `time.repr`
  - Описана структура pipeline Promtail с учётом извлечения `record` и mapping `level` → `level_name`
  - Добавлены примечания о корректной обработке записей без `extra` или без полей `event`/`status`

---

## [6.5.0] 2025-12-05 — Интеграция Loki/Grafana/Promtail и улучшение инфраструктуры

### Добавлено

- **Интеграция Loki/Grafana/Promtail для централизованного логирования**:
  - Добавлены сервисы `loki`, `grafana` и `promtail` в `docker-compose.yml` с соответствующими volumes, портами и healthcheck'ами
  - Создан `monitoring/loki-config.yml` с файловым backend и retention 7 дней для dev/stage окружения
  - Создан `monitoring/promtail-config.yml` с pipeline для чтения JSONL-логов из `wednesday_bot.events.jsonl`, парсинга JSON полей (`time`, `level`, `message`, `extra`), использования `time` как timestamp и продвижения `level`, `service`, `env`, `event`, `status` в Loki labels
  - Создан `monitoring/grafana/provisioning/datasources/datasource-loki.yml` для автоматической настройки Loki как datasource в Grafana
  - Создан `monitoring/grafana/provisioning/dashboards/dashboard.yml` для файлового provisioning дашбордов
  - Создан `monitoring/grafana/provisioning/dashboards/wednesday-logs-dashboard.json` с дашбордом "Wednesday Bot Logs", включающим templating переменные (`env`, `service`, `level`, `event`, `status`) и панели для log rate, event types, generation latency и recent logs
  - Создан `monitoring/grafana/provisioning/alerting/logging-rules.yml` с правилами алёртинга для "High error rate in logs" и "Suspicious secret patterns in logs"
  - Создан `docs/dev/logger_loki_schema.md` с формальной схемой JSON-логов для Loki/Promtail (версия v1)
  - Создан `docs/logging_loki_validation.md` с детальным гайдом по валидации стека логирования и рекомендациями по поэтапному внедрению (dev → stage → prod)
  - Интеграция реализована минимально инвазивно: существующий код логирования не изменён, защита секретов через `mask_secrets` и `scrub` сохранена, Promtail только читает уже маскированные JSON-строки из volume `logs`

### Изменено

- **Миграция Celery worker с asyncio на threads pool**:
  - Удалён скрипт `scripts/celery_worker_asyncio.py` — теперь используется прямой CLI в `docker-compose.yml`
  - Обновлён `docker-compose.yml`: команда запуска worker использует `celery -A services.celery_app worker --pool=threads --loglevel=info --concurrency=8 -Q wednesday,images,maintenance`
  - Исправлен healthcheck в `docker-compose.yml`: заменён удалённый `scripts/celery_healthcheck.py` на стандартный `celery inspect ping`
  - Обновлены комментарии и документация: убраны упоминания про "asyncio pool через Python API"
  - Обновлён `README.md`: команда запуска worker теперь использует `--pool=threads`
  - **Причина**: В Celery 5.x пул asyncio не поддерживается вообще (ни через CLI, ни через Python API). Threads pool официально поддерживается через CLI и корректно работает с async/await задачами для I/O-bound операций.

- **Упрощение логики подключения Celery к Redis**:
  - Удалена избыточная функция `_update_redis_url()` и её вызовы через сигнал `on_after_configure` в `services/celery_app.py`
  - Упрощены комментарии: убраны упоминания про обновление URL через сигналы, так как все параметры broker устанавливаются сразу после создания app
  - Добавлено экранирование пароля Redis через `urllib.parse.quote()` в `utils/redis_client.py` для корректной работы с паролями, содержащими специальные символы (например, `!`)
  - Все параметры broker URL (`broker_url`, `broker`, `result_backend`, `broker_read_url`, `broker_write_url`) устанавливаются сразу после создания Celery app, что исключает необходимость дополнительного обновления
  - Упрощена команда запуска worker в `docker-compose.yml`: убрана установка `CELERY_BROKER_URL` через `sh -c`, используется прямой вызов `celery` с правильным `REDIS_HOST=redis` из переменных окружения
  - Добавлена маскировка пароля Redis в логах в `services/celery_app.py`: пароль в Redis URL заменяется на `****` перед логированием для предотвращения утечки секретов

- **Улучшение healthcheck для сервисов**:
  - **bot**: упрощена команда healthcheck до однострочной Python-команды (убрана многострочная конструкция), увеличен `start_period` с 30s до 60s для времени на инициализацию
  - **celery-beat**: изменён подход к healthcheck — вместо проверки процесса и подключения к Redis теперь проверяется наличие и свежесть файла лога `/app/logs/beat.log` (обновлён менее 60 секунд назад), добавлен `--logfile=/app/logs/beat.log` в команду запуска beat, увеличен `start_period` с 30s до 60s
  - **promtail**: изменена команда healthcheck с `ps aux | grep` на `/bin/pidof promtail` для более надёжной проверки процесса, увеличен `start_period` с 20s до 40s
  - **loki**: исправлен healthcheck для использования `wget -q -O- http://localhost:3100/ready | grep -q ready` (busybox wget доступен в образе grafana/loki)
  - **grafana**: добавлен healthcheck с проверкой HTTP endpoint `/api/health` через `wget`, установлен `start_period: 60s` для времени на инициализацию

### Исправлено

- **Исправление ложных срабатываний pre-commit хука `detect-private-key`**:
  - Заменён паттерн "BEGIN_PRIVATE_KEY" (с подчёркиванием) вместо варианта с пробелом в следующих файлах:
    - `docs/logging_loki_validation.md` — в примере тестирования
    - `monitoring/grafana/provisioning/alerting/logging-rules.yml` — в LogQL запросе и описании алёрта
    - `docs/logger_loki_schema.md` — в документации
    - `docs/dev/logging_loki_grafana_plan.md` — в двух местах
  - Изменение сохраняет смысл как паттерн для поиска в логах, но предотвращает ложные срабатывания детектора приватных ключей

- **Исправление ошибки `KeyError: 'No such transport: '` в celery-worker**:
  - Проблема была вызвана некорректным парсингом Redis URL с паролем, содержащим специальные символы (например, `!`)
  - Решение: добавлено экранирование пароля через `urllib.parse.quote()` в `utils/redis_client.py` и принудительная установка всех broker URL параметров сразу после создания Celery app
  - Упрощена логика получения Redis URL: убрана зависимость от `CELERY_BROKER_URL` при импорте, используется только `get_redis_url()`, который читает `REDIS_HOST` из переменных окружения

- **Исправление ошибки `ValueError: Signal receiver must accept keyword arguments`**:
  - Функция `_update_redis_url()` была обновлена для принятия `*args` и `**kwargs` для совместимости с сигналами Celery
  - Впоследствии функция была удалена как избыточная, так как все параметры broker устанавливаются сразу после создания app

---

## [6.4.3] 2025-12-04 — Усиление защиты секретов в логах

### Добавлено
- Централизованная функция `mask_secrets(text)` в `utils.logger`, выполняющая детерминированную точечную маскировку **известных** длинных секретных значений (в первую очередь `GIGACHAT_AUTHORIZATION_KEY`) перед выводом в текстовые и JSON-логи.
- Функция `scrub(obj)` для рекурсивной очистки структурированных данных (`extra` в JSON-логах) по ключам из расширенного списка чувствительных слов (`token`, `secret`, `access_token`, `refresh_token`, `client_secret`, `private_key`, `secret_key`, `cookie`, и т.д.).
- Фильтр для JSON-sink `wednesday_bot.events.jsonl`, автоматически применяющий `mask_secrets` к полю `message` и `scrub` к полю `extra` для всех записей, независимо от места вызова логгера.
- Документация `docs/dev/logger_secrets_overview.md` с описанием правил безопасного логирования, работы `mask_secrets`/`scrub` и списка чувствительных ключей.

### Изменено
- `log_event(...)` теперь прогоняет человеко‑читаемое сообщение (`message` или `event`) через `mask_secrets` перед логированием, что предотвращает попадание известных секретных значений в текстовые и JSON-логи без изменения формата записей.
- Расширен список `_SENSITIVE_KEYWORDS`, используемый как в `log_execution` (маскировка чувствительных kwargs), так и в `scrub(obj)` (маскировка значений по ключам), при этом поведение ограничено только проверкой по ключам без "умного" анализа произвольных строк.
- Поведение `GigaChatTextClient` зафиксировано тестами: при логировании ключа авторизации в debug-логах используется только безопасный preview (длина + короткий префикс), а полный `authorization_key` не попадает в логи.

### Исправлено
- Гарантированно предотвращена утечка значений `GIGACHAT_AUTHORIZATION_KEY` и других длинных секретов в JSON-логах (включая вложенные структуры внутри `extra` и прямые `logger.bind(...)`), за счёт комбинированного применения `mask_secrets` и `scrub` на уровне sink.
- Уменьшен риск случайного логирования access token'ов, refresh token'ов, client_secret и подобных полей при добавлении новых мест логирования: любые новые структурированные записи автоматически проходят через фильтр JSON-sink без доработки бизнес-кода.

---

## [6.4.2] 2025-12-04 — Вторая итерация рефакторинга E2E-инфраструктуры Celery

### Добавлено
- **Тестовый settings-слой**:
  - Создан модуль `utils.config_test` с `TestConfig`, описывающим настройки только для тестовой среды (Redis, Postgres, логирование).
  - Тестовый Celery app читает URL Redis из `CELERY_TEST_REDIS_URL` через `config_test`, полностью изолируясь от боевого `utils.config` и `utils.redis_client`.
- **Общая утилита и фикстура готовности Celery worker**:
  - Добавлен `tests/common/wait_for_celery.py` с функцией `wait_for_celery_worker()`, которая с ретраями отправляет `test.ping` в очередь `test_main` и ждёт `"pong"`.
  - Добавлен `tests/fixtures/celery_worker_ready.py` с session-fixture `celery_worker_ready` (`autouse=True`), использующей новую утилиту.
- **Новый поведенческий e2e-набор Celery**:
  - Создан `tests/e2e/celery/test_celery_e2e_basic.py` с короткими сценариями:
    - базовый `test.ping` → `"pong"`;
    - проверка работы result backend;
    - конкурентное выполнение нескольких задач.
- **Запуск pytest внутри Docker-контейнера**:
  - В `docker-compose.test.yml` добавлен сервис `tests`, собираемый из `Dockerfile.test` и использующий то же окружение, что и `celery-worker-test` (Postgres/Redis в тестовой сети, `CELERY_TEST_REDIS_URL` и т.д.).
  - Цели `make test`, `make test-cov`, `make test-e2e` теперь запускают pytest внутри контейнера `tests` через `docker compose ... run --rm tests ...`.
- **Скрипты оркестрации тестового окружения**:
  - Добавлены `scripts/test_up.sh`, `scripts/test_down.sh`, `scripts/run_e2e.sh`, инкапсулирующие подъем/остановку `docker-compose.test.yml` и запуск e2e-набора.

### Изменено
- **Healthcheck Celery worker в тестовом docker-compose**:
  - Для `celery-worker-test` healthcheck переведён с проверки процесса через `pgrep` на поведенческую проверку `celery -A services.celery_app_test inspect ping --timeout=2`.
  - В `docker-compose.test.yml` для сервисов `celery-worker-test` и `tests` явно заданы `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` и `CELERY_TEST_REDIS_URL` на `redis_test:6379`, чтобы избежать скрытого fallback-а на `localhost`.
- **Тестовый Celery app**:
  - `services.celery_app_test` больше не импортирует `utils.redis_client.get_redis_url` и не зависит от боевого конфигурационного модуля.
  - Брокер и result backend Celery теперь настраиваются только через тестовые env/`utils.config_test`, что делает тестовый app полностью самостоятельным.
- **Структура тестов Celery**:
  - Логика ожидания worker’а перенесена из `tests/utils/wait_for_celery.py` в `tests/common/wait_for_celery.py` и `tests/fixtures/celery_worker_ready.py`.
  - Поведенческие e2e-сценарии вынесены в `tests/e2e/celery/`, а инфраструктурные/диагностические проверки Celery (inspect/stats/beat/timezone и т.п.) остались в `tests/test_services/test_celery_e2e.py` и помечены маркером `@pytest.mark.infra`.
  - В pytest-конфиге (`pyproject.toml`) зарегистрирован новый маркер `infra`, чтобы явно отделить редкий инфраструктурный набор от основного e2e.
- **Makefile и запуск тестов**:
  - Цели `test` и `test-cov` больше не запускают pytest на хосте, а используют `docker compose ... run --rm tests pytest ...`, что гарантирует идентичное окружение с `celery-worker-test`.
  - Цель `test-e2e` (`scripts/run_e2e.sh`) теперь также выполняет e2e-набор внутри контейнера `tests`, с фильтрацией по маркеру `e2e and not infra`.
- **Документация по Celery E2E**:
  - В `docs/dev/celery_e2e_testing_notes.md` добавлен раздел про вторую итерацию рефакторинга: новый healthcheck, упрощённую readiness-логику и разделение e2e/infra-наборов.
  - Обновлён `tests/README.md` с описанием новой структуры каталогов (`tests/e2e/celery/`, `tests/common/`, `tests/fixtures/`), правилами маркеров `e2e`/`infra` и примерами запуска поведенческих и инфраструктурных наборов.

### Удалено
- Удалён устаревший модуль `tests/utils/wait_for_celery.py`; его функциональность заменена более простым `tests/common/wait_for_celery.py` и отдельной фикстурой `tests/fixtures/celery_worker_ready.py`.

---

## [6.4.1] 2025-12-04 — Упрощение и изоляция E2E-инфраструктуры Celery

### Добавлено
- **Отдельный тестовый Celery app**:
  - Создан `services/celery_app_test.py` — минимальный Celery-приложение для тестов, использующее только Redis и не импортирующее боевой код бота и сервисов.
  - Создан `services/celery_tasks_test.py` с единственной задачей `test.ping`, используемой для healthcheck и E2E-тестов.
- **Ожидание готовности Celery worker в тестах**:
  - Добавлен модуль `tests/utils/wait_for_celery.py` с синхронной функцией `wait_for_celery_worker()`, проверяющей:
    - доступность Redis;
    - регистрацию очередей через `inspect().active_queues()`;
    - успешное выполнение задачи `test.ping` в очереди `test_main`.
  - Добавлена session-fixture `celery_worker_ready` с `autouse=True`, гарантирующая готовность worker перед запуском E2E-тестов.

### Изменено
- **Тестовый Docker-образ и docker-compose для E2E**:
  - Добавлен `Dockerfile.test`, собирающий минимальный образ только из `services/`, `utils/`, `bot/` и `requirements.txt` с `ENV TESTING=1` до копирования кода.
  - Упрощён `docker-compose.test.yml`:
    - оставлены только сервисы `postgres_test`, `redis_test`, `celery-worker-test`;
    - `celery-worker-test` собирается из `Dockerfile.test` и использует `services.celery_app_test` с тестовыми очередями (`test_main`, `test_images`, `test_maintenance`);
    - healthcheck worker-а переведён на простой `pgrep 'celery worker'` без Python-скриптов и импорта приложения.
- **Логирование в тестах**:
  - В `utils/logger.py` добавлена ветка для `TESTING=1`: в тестовой среде логи пишутся только в stdout, файловые sink-ы не создаются.
- **Запуск тестовой инфраструктуры через Makefile**:
  - Цель `test-up` переведена на использование `docker compose` и, при наличии `timeout`/`gtimeout`, ограничена по времени (для CI); на macOS запуск выполняется без таймаута.
  - Цели `test`, `test-cov`, `test-e2e` теперь загружают окружение из `.env.test`, фильтруя комментарии и пустые строки, и не дублируют переменные вручную.
- **E2E-тесты Celery**:
  - `tests/test_services/test_celery_e2e.py` переведён на использование `services.celery_app_test` и тестовых очередей.
  - Проверка доступности worker теперь основана на `inspect.ping()` и регистрации задачи `test.ping`, а не на производственных задачах и очередях.
  - Тесты, завязанные на Beat и retry-механику, адаптированы к тестовому app и проверяют структуру конфигурации либо выполнение `test.ping`, не полагаясь на боевое расписание.
- **Конфигурация тестового окружения**:
  - Создан `.env.test`, описывающий тестовые переменные окружения для E2E (Postgres, Redis, TESTING, расписание), с использованием `localhost` для доступа к проброшенным портам.
  - Обновлён `tests/README.md` с новыми инструкциями по запуску E2E-тестов через `make test-up` / `make test-e2e` / `make test-down`.

### Удалено
- Удалён скрипт `scripts/celery_healthcheck.py`; проверка готовности Celery worker в тестовой инфраструктуре теперь выполняется:
  - на уровне Docker healthcheck через `pgrep`;
  - на уровне pytest через задачу `test.ping` и `wait_for_celery_worker()`.

---

## [6.4.0] 2025-12-03 — Миграция планировщика задач на Celery с поддержкой распределённых worker'ов

### Добавлено
- **Миграция на Celery для планирования задач**:
  - Добавлена зависимость `celery[asyncio]==5.5.3` в `requirements.txt` и `pyproject.toml` (уже была добавлена ранее).
  - Создан модуль `services/celery_app.py` с конфигурацией Celery:
    - Использует Redis как брокер и backend для задач.
    - Настроена поддержка async задач через `celery[asyncio]`.
    - Настроены очереди: `wednesday` (отправка жаб), `images` (генерация изображений), `maintenance` (ежедневные задачи).
    - Настроены retry-механики с экспоненциальным backoff только для сетевых ошибок.
    - Настроен Dead Letter Queue (DLQ) для задач, упавших после всех retry.
    - Настроена интеграция логирования Celery через Loguru.
  - Создан модуль `services/celery_tasks.py` с Celery задачами:
    - `wednesday.send_frog` — отправка изображения жабы по средам.
    - `wednesday.generate_image` — генерация изображения жабы.
    - `wednesday.daily_cleanup` — ежедневная очистка старых данных.
    - `wednesday.daily_statistics` — ежедневный сбор статистики.
  - Реализован класс `CeleryServices` с lazy инициализацией для fork safety:
    - Все async ресурсы (Redis, Postgres, WednesdayBot, ImageGenerator) создаются ПОСЛЕ fork worker процесса.
    - Инициализация происходит внутри задач, что исключает race conditions.
    - Реализован graceful shutdown для корректного закрытия async ресурсов.
  - Реализован декоратор `@log_celery_task` для автоматического логирования задач:
    - Логирование начала, успеха и ошибок задач.
    - Измерение времени выполнения.
    - Структурированные события через `log_event()`.
  - Реализована функция `is_retryable_error()` для фильтрации retryable ошибок:
    - Retry только для сетевых ошибок (aiohttp.ClientError, TimeoutError, ConnectionError и др.).
    - Бизнес-логические ошибки не retry, сразу падают.

- **Конфигурация Celery** (`utils/config.py`):
  - Добавлены новые свойства конфигурации:
    - `scheduler_tz` — часовой пояс для Celery Beat (по умолчанию "Europe/Amsterdam").
    - `scheduler_send_times` — времена отправки в среду (по умолчанию ["09:00", "12:00", "18:00"]).
    - `scheduler_wednesday_day` — день недели для отправки (по умолчанию 2 — среда).
    - `use_old_scheduler` — флаг для использования старого TaskScheduler (для обратной совместимости).

- **Метрики Prometheus для Celery** (`utils/prometheus_metrics.py`):
  - Добавлен счётчик `CELERY_TASKS_TOTAL` для отслеживания количества задач:
    - Labels: `task_name` (имя задачи), `status` (статус: "started", "success", "failed").
  - Добавлена гистограмма `CELERY_TASK_DURATION_SECONDS` для отслеживания времени выполнения:
    - Labels: `task_name` (имя задачи).
    - Бакеты: 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0 секунд.
  - Добавлен счётчик `CELERY_TASK_RETRIES_TOTAL` для отслеживания retry-попыток:
    - Labels: `task_name` (имя задачи).
  - Добавлен счётчик `CELERY_TASK_FAILURES_TOTAL` для отслеживания неудачных задач:
    - Labels: `task_name` (имя задачи), `error_type` (тип ошибки).
  - Добавлен gauge `CELERY_QUEUE_LENGTH` для отслеживания длины очередей:
    - Labels: `queue_name` (имя очереди).
  - Добавлен gauge `CELERY_ACTIVE_TASKS` для отслеживания активных задач:
    - Labels: `worker_name` (имя worker'а).

- **Интеграция Celery в healthcheck** (`services/healthcheck.py`):
  - Добавлена функция `_check_celery()` для проверки доступности Celery workers.
  - Проверка выполняется через `celery_app.control.ping()`.
  - Статус Celery включён в ответ `/health` endpoint (не критичен для общего статуса).

- **Docker и инфраструктура**:
  - Обновлён `Dockerfile`:
    - Добавлена установка `tzdata` для корректной работы Celery Beat с timezone.
    - Установлена переменная окружения `TZ=Europe/Amsterdam`.
    - Добавлена установка `gosu` для безопасного переключения пользователя в entrypoint.
    - Созданы директории `/app/logs` и `/app/data` с правильными правами доступа.
    - Добавлен `docker-entrypoint.sh` для идемпотентной подготовки окружения (создание директорий, установка прав, переключение пользователя).
  - Обновлён `docker-compose.yml`:
    - Добавлен сервис `celery-worker` для выполнения задач:
      - Использует asyncio pool через Python API (`scripts/celery_worker_asyncio.py`) для совместимости с Celery 5.5.3.
      - Обрабатывает очереди: `wednesday`, `images`, `maintenance`.
      - Настроен healthcheck через `scripts/celery_healthcheck.py` с использованием `celery_app.control.ping()`.
      - Добавлены volumes для логов и данных.
    - Добавлен сервис `celery-beat` для планирования задач:
      - Отдельный процесс от worker'а (разделение Beat и Worker).
      - Настроена поддержка timezone через переменную `TZ`.
      - Добавлен volume `beat_data` для сохранения состояния расписания.
  - Обновлён `docker-compose.test.yml`:
    - Добавлены сервисы `celery-worker-test` и `celery-beat-test` для E2E тестирования.
    - Настроены тестовые переменные окружения и volumes.
    - Добавлен healthcheck для `celery-worker-test` с увеличенным `start_period` для инициализации.
    - Включено логирование только в stdout (`LOG_TO_STDOUT_ONLY=1`) для избежания проблем с правами доступа.
  - Создан `docker-entrypoint.sh`:
    - Идемпотентная подготовка директорий (`/app/logs`, `/app/data/prompts`, `/app/data/beat`).
    - Установка прав доступа для пользователя `app`.
    - Безопасное переключение пользователя через `gosu`.
  - Созданы вспомогательные скрипты:
    - `scripts/celery_worker_asyncio.py` — запуск Celery worker с asyncio pool через Python API.
    - `scripts/celery_healthcheck.py` — проверка здоровья worker через `celery_app.control.ping()`.

- **Тесты для Celery**:
  - Создан файл `tests/test_services/test_celery_tasks.py` с unit-тестами:
    - Тестирование lazy инициализации `CeleryServices`.
    - Тестирование функции `is_retryable_error()`.
    - Тестирование успешного выполнения задач.
    - Тестирование retry при сетевых ошибках.
    - Тестирование отсутствия retry для бизнес-логических ошибок.
    - Тестирование graceful shutdown.
  - Создан файл `tests/test_services/test_celery_integration.py` с integration-тестами:
    - Тестирование конфигурации расписания Celery Beat.
    - Тестирование маршрутизации задач по очередям.
    - Тестирование общей конфигурации Celery приложения.
    - Тестирование регистрации задач.
  - Создан файл `tests/test_services/test_celery_e2e.py` с E2E тестами:
    - Тестирование доступности Celery worker через `control.ping()`.
    - Тестирование отправки задач в очереди.
    - Тестирование маршрутизации задач по очередям.
    - Тестирование регистрации расписания в Celery Beat.
    - Тестирование мониторинга длины очередей.
    - Тестирование result backend (Redis).
    - Тестирование конкурентного выполнения задач.
    - Тестирование статистики worker'а.
    - Тестирование механизма retry (структурная проверка).
    - Тестирование корректности timezone в расписании.
  - Маркировка E2E тестов:
    - Добавлен маркер `e2e` в `pyproject.toml` для селективного запуска E2E тестов.
    - Помечены существующие тесты, использующие реальные контейнеры Postgres и Redis (56 тестов).
    - Обновлён `tests/README.md` с инструкциями по запуску E2E тестов.

- **Документация**:
  - Обновлён `README.md` с разделом о Celery:
    - Описание архитектуры (Beat, Worker, Redis).
    - Инструкции по запуску через Docker Compose и вручную.
    - Описание очередей задач и их concurrency.
    - Конфигурация через переменные окружения.
    - Информация о мониторинге и метриках.
  - Обновлён `env_example.txt` с переменными окружения для Celery:
    - Настройки worker'а (concurrency, prefetch multiplier).
    - Настройки Beat (max loop interval).
    - Настройки retry (max retries, backoff, jitter).
    - Настройки DLQ.
    - Флаг `USE_OLD_SCHEDULER` для обратной совместимости.
  - Обновлён `tests/README.md`:
    - Добавлены инструкции по запуску E2E тестов для Celery.
    - Описание требований к тестовым контейнерам.

- **Утилиты**:
  - Добавлена функция `get_redis_url()` в `utils/redis_client.py`:
    - Возвращает URL Redis для использования в Celery.
    - Поддерживает как `REDIS_URL`, так и отдельные параметры (host, port, db, password).
    - Корректно обрабатывает пустой пароль (не добавляет `:` в URL при отсутствии пароля).
  - Обновлён `utils/logger.py`:
    - Добавлена поддержка переменной окружения `LOG_TO_STDOUT_ONLY` для логирования только в stdout.
    - Полезно для тестовых контейнеров и окружений без доступа к файловой системе.
    - Файловые sinks добавляются только если `LOG_TO_STDOUT_ONLY` не установлен.

### Изменено
- **WednesdayBot** (`bot/wednesday_bot.py`):
  - Добавлена поддержка опционального использования старого `TaskScheduler`:
    - `TaskScheduler` создаётся только если `USE_OLD_SCHEDULER=true`.
    - По умолчанию используется Celery (запускается отдельно через `celery worker/beat`).
    - Метод `setup_scheduler()` проверяет наличие scheduler перед настройкой.
    - Метод `start()` запускает scheduler только если он инициализирован.
    - Метод `stop()` останавливает scheduler только если он был запущен.
    - Сообщение о запуске показывает, какой планировщик используется (Celery или TaskScheduler).
  - Метод `send_wednesday_frog()` обновлён для работы без scheduler:
    - Использует `config.scheduler_send_times` для получения времён отправки, если scheduler не инициализирован.
  - Тесты `test_on_my_chat_member_added` и `test_on_my_chat_member_removed` помечены как E2E.

- **Healthcheck** (`services/healthcheck.py`):
  - Добавлена проверка доступности Celery workers в `_build_health_payload()`.
  - Статус Celery включён в ответ `/health`, но не влияет на общий статус (не критичен для работы бота).
  - Проверка выполняется через `celery_app.control.ping()` с использованием `asyncio.to_thread()` для совместимости с async контекстом.

- **Makefile**:
  - Добавлена команда `test-e2e` для запуска E2E тестов.
  - Обновлена команда `test-up`:
    - Добавлено ожидание готовности `celery-worker-test` и `celery-beat-test`.
    - Добавлен вывод логов Celery worker при ошибке healthcheck для упрощения диагностики.
    - Добавлен таймаут ожидания готовности сервисов (60 секунд).
  - Добавлена переменная `REDIS_PASSWORD=""` в команды тестирования для явного указания отсутствия пароля.

- **Тесты**:
  - Обновлены unit-тесты Celery задач для корректной работы с декораторами:
    - Используется последовательный обход декораторов через `__wrapped__` и `__func__` для получения исходной функции.
    - Исправлены вызовы задач с `bind=True` для правильной передачи аргументов.
    - Исправлены патчи для async функций в тестах shutdown.
  - Помечены существующие E2E тесты (56 тестов):
    - Тесты для `ChatsStore`, `DispatchRegistry`, `ModelsStore`, `AdminsStore`, `ImagesStore`, `PromptsStore`, `UsageTracker`, `Metrics`.
    - Тесты для SQL миграций.
    - Тесты для команд бота, использующих реальные Postgres stores.

### Технические детали
- **Fork safety**: Все async ресурсы создаются ПОСЛЕ fork worker процесса через lazy инициализацию в `CeleryServices`.
- **Lazy factories**: Инициализация сервисов происходит внутри задач, что исключает race conditions и проблемы с prefetch.
- **Graceful shutdown**: Реализован корректный shutdown для async ресурсов через сигнал `worker_shutdown`.
- **Retry-механики**: Retry только для сетевых ошибок, бизнес-логические ошибки не retry (сразу падают в DLQ после max_retries).
- **Разделение Beat и Worker**: Beat и Worker запускаются в отдельных процессах/контейнерах для избежания race conditions при reload.
- **Asyncio pool через Python API**: Для production используется скрипт `scripts/celery_worker_asyncio.py`, запускающий worker через `celery_app.worker_main(["--pool=asyncio"])`, так как прямой CLI `celery -P asyncio` не поддерживается в Celery 5.5.3.
- **Healthcheck через Celery API**: Проверка здоровья worker выполняется через `celery_app.control.ping()` вместо проверки процесса, что более надёжно.
- **Idempotent entrypoint**: Скрипт `docker-entrypoint.sh` обеспечивает идемпотентную подготовку окружения (создание директорий, установка прав, переключение пользователя) без нарушения работы контейнера при повторном запуске.
- **Логирование в тестах**: Для тестовых контейнеров включено логирование только в stdout через `LOG_TO_STDOUT_ONLY=1` для избежания проблем с правами доступа и volumes.

### Обратная совместимость
- Старый `TaskScheduler` остаётся доступным через флаг `USE_OLD_SCHEDULER=true`.
- По умолчанию используется Celery, но можно вернуться к старому планировщику при необходимости.
- Все существующие команды и API остаются без изменений.

---

## [6.3.0] 2025-12-03 — Внедрение retry-механик с экспоненциальным backoff для HTTP-клиентов

### Добавлено
- **Библиотека tenacity для retry-механик**:
  - Добавлена зависимость `tenacity>=8.2.3` в `requirements.txt` и `pyproject.toml`.
  - Используется для реализации автоматических повторных попыток HTTP-запросов с экспоненциальным backoff.

- **Модуль retry-утилит** (`utils/retry.py`):
  - Создан новый модуль с декораторами для автоматических retry HTTP-запросов:
    - `@retry_critical` — 5 попыток для критичных операций (например, получение токена доступа).
    - `@retry_standard` — 3 попытки для стандартных HTTP-запросов.
    - `@retry_optional` — 2 попытки для необязательных операций.
    - `@retry_with_logging` — универсальный декоратор с настройками из конфигурации.
  - Реализована автоматическая обработка сетевых ошибок:
    - `aiohttp.ClientConnectorError` — ошибки подключения.
    - `aiohttp.ServerTimeoutError` — таймауты сервера.
    - `TimeoutError` — общие таймауты.
    - `aiohttp.ClientError` — другие ошибки клиента.
  - Исключение из retry для определённых HTTP-статусов:
    - 400 (Bad Request) — ошибка клиента, не требует retry.
    - 401 (Unauthorized) — проблемы с авторизацией, не требуют retry.
    - 403 (Forbidden) — нет доступа, не требует retry.
  - Автоматическое логирование каждой попытки retry через `log_event()` с полями:
    - `event`: `"{service}_retry"` (например, `"kandinsky_retry"`, `"gigachat_retry"`).
    - `attempt`: номер текущей попытки.
    - `max_attempts`: максимальное количество попыток.
    - `error`: тип ошибки.
    - `wait_time`: время ожидания до следующей попытки.
    - `method`: имя метода.
  - Логирование финальной ошибки после исчерпания всех попыток с уровнем `error`.

- **Конфигурация retry** (`utils/config.py`):
  - Добавлены новые свойства конфигурации для настройки retry-механик:
    - `retry_max_attempts` — максимальное количество попыток (по умолчанию 5, настраивается через `RETRY_MAX_ATTEMPTS`).
    - `retry_multiplier` — множитель для экспоненциального backoff (по умолчанию 1.0, настраивается через `RETRY_MULTIPLIER`).
    - `retry_min_wait` — минимальное время ожидания между попытками в секундах (по умолчанию 2.0, настраивается через `RETRY_MIN_WAIT`).
    - `retry_max_wait` — максимальное время ожидания между попытками в секундах (по умолчанию 30.0, настраивается через `RETRY_MAX_WAIT`).

- **Метрики retry** (`utils/prometheus_metrics.py`):
  - Добавлен счётчик `HTTP_RETRIES_TOTAL` для отслеживания количества retry-попыток:
    - Labels: `service` (имя сервиса), `method` (имя метода), `status` (статус: "retry" или "failed").
  - Добавлена гистограмма `HTTP_RETRY_WAIT_SECONDS` для отслеживания времени ожидания между попытками:
    - Labels: `service` (имя сервиса), `method` (имя метода).
    - Бакеты: 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0 секунд.

- **Тесты для retry-механик** (`tests/test_utils/test_retry.py`):
  - Создан новый файл с комплексными тестами:
    - Тестирование успешного выполнения без retry.
    - Тестирование retry при различных типах ошибок (`ClientConnectorError`, `TimeoutError`).
    - Тестирование исчерпания всех попыток и выбрасывания исключения.
    - Тестирование отсутствия retry для HTTP-статусов 400, 401, 403.
    - Тестирование различных стратегий retry (critical, standard, optional).
    - Тестирование логирования retry через `log_event`.
    - Тестирование обновления метрик Prometheus.
    - Тестирование экспоненциального backoff.
    - Тестирование отсутствия retry для не-retryable исключений.
    - Тестирование retry для HTTP 500 (Internal Server Error).

### Изменено
- **KandinskyClient** (`services/clients/kandinsky.py`):
  - Все HTTP-запросы обёрнуты в retry-декораторы:
    - `_get_pipeline_id()` — обёрнут в `@retry_standard` для получения pipeline ID.
    - `_start_generation()` — обёрнут в `@retry_standard` для запуска генерации.
    - `_wait_for_generation()` — запросы статуса внутри цикла polling обёрнуты в `@retry_standard`.
    - `check_api_status()` — обёрнут в `@retry_standard` для проверки статуса API.
    - `set_model()` — обёрнут в `@retry_standard` для установки модели.
  - Сохранены существующие таймауты для каждого типа запроса.
  - Retry применяется только к отдельным HTTP-запросам, а не к операциям верхнего уровня (например, `_wait_for_generation()` имеет собственный цикл polling, retry применяется только к запросам статуса внутри цикла).

- **GigaChatTextClient** (`services/clients/gigachat_text.py`):
  - Все HTTP-запросы обёрнуты в retry-декораторы:
    - `_get_access_token()` — обёрнут в `@retry_critical` для получения токена доступа (критичная операция, 5 попыток).
    - `generate()` — обёрнут в `@retry_standard` для генерации промпта.
    - `get_available_models()` — обёрнут в `@retry_standard` для получения списка моделей.
  - Retry для `_get_access_token()` применён внутри существующего `_token_lock` для предотвращения race conditions.
  - Сохранены существующие таймауты для каждого типа запроса.

- **Тесты GigaChatTextClient** (`tests/test_services/test_gigachat_text_client.py`):
  - Обновлён класс `_DummySession` для совместимости с retry-механикой:
    - Методы `post()` и `get()` сделаны асинхронными (`async def`).
  - Обновлён класс `_DummyResponse` для полной совместимости с `aiohttp.ClientResponse`:
    - Добавлено поле `headers` для корректной работы с retry.

---

## [6.2.1] 2025-12-03 — Удаление устаревшего синхронного клиента GigaChat и добавление документации по Sentry

### Удалено
- **Устаревший синхронный клиент GigaChat** (`services/prompt_generator.py`):
  - Удалён класс `GigaChatClient`, который использовал синхронный `requests` и не применялся в продакшене.
  - Клиент был заменён на асинхронный `GigaChatTextClient` из `services/clients/gigachat_text.py` в версии 6.1.0.
  - В модуле `services/prompt_generator.py` остался только класс `PromptStorage` для файлового хранения промптов.
  - Удалены неиспользуемые импорты и константы, связанные с синхронным клиентом (`requests`, `time`, `uuid` и др.).
  - Обновлён docstring модуля с указанием причины удаления и ссылкой на актуальный клиент.

- **Тесты и фикстуры для устаревшего клиента**:
  - Удалены все тесты для `GigaChatClient` из `tests/test_services/test_prompt_generator.py` (8 тестов).
  - Оставлены только тесты для `PromptStorage` (4 теста), которые остаются актуальными.
  - Удалена фикстура `patch_gigachat_client` из `tests/conftest.py`, так как она больше не требуется.

### Изменено
- **Тесты типизации** (`tests/test_typing.py`):
  - Заменён импорт `GigaChatClient` на `PromptStorage` для соответствия обновлённой структуре модуля.

- **Документация конфигурации** (`env_example.txt`):
  - Добавлена секция "SENTRY МОНИТОРИНГ ОШИБОК" с описанием трёх опциональных переменных окружения:
    - `SENTRY_DSN` — DSN для интеграции с Sentry (обязательно для включения мониторинга ошибок).
    - `SENTRY_ENVIRONMENT` — название окружения для фильтрации ошибок (production, staging, development и т.д.).
    - `RELEASE` — версия релиза для отслеживания ошибок по версиям (git-хэш или семантическая версия).
  - Добавлены комментарии с примерами значений и ссылками на документацию Sentry.

---

## [6.2.0] 2025-12-03 — Динамическая замена LLM‑клиентов в рантайме и унификация интерфейсов

### Добавлено
- **Динамический контейнер текстового клиента**:
  - Новый класс `services.clients.text_client_container.TextClientContainer`, реализующий `ITextToTextClient` и выступающий как стабильная точка доступа к текущему LLM‑клиенту.
  - Поддерживает прозрачное делегирование методов `generate()`, `check_api_status()`, `get_available_models()`, `set_model()` к активному клиенту.
  - Добавлен singleton‑доступ через функцию `services.clients.text_client_container.get_text_client_container()`, также реэкспортированную из `services.clients`.
  - Реализована безопасная замена клиента в рантайме через `await replace_client(new_client)`: старый клиент корректно закрывается через его `aclose()` (если он реализован), все существующие сервисы продолжают работать через тот же контейнер.

- **Динамический контейнер клиента генерации изображений**:
  - Новый класс `services.clients.image_client_container.ImageClientContainer`, реализующий `ITextToImageClient` и выступающий как стабильная точка доступа к текущему TTI‑клиенту.
  - Поддерживает прозрачное делегирование методов `generate()`, `check_api_status()`, `get_available_models()`, `set_model()` к активному клиенту.
  - Добавлен singleton‑доступ через функцию `services.clients.image_client_container.get_image_client_container()`, также реэкспортированную из `services.clients`.
  - Реализована безопасная замена клиента в рантайме через `await replace_client(new_client)` с использованием `asyncio.Lock` для предотвращения race conditions при параллельных вызовах; старый клиент корректно закрывается через его `aclose()` (если он реализован), все существующие сервисы продолжают работать через тот же контейнер.
  - Контейнер безопасно обрабатывает отсутствие клиента и клиентов без опциональных методов, возвращая безопасные значения по умолчанию и логируя предупреждения.

- **Унификация интерфейсов клиентов**:
  - Интерфейс `ITextToImageClient` расширен методами `check_api_status()`, `get_available_models()` и `set_model()` для полного соответствия с `ITextToTextClient`.
  - Оба интерфейса теперь имеют единообразный набор методов управления моделями и проверки статуса, что упрощает работу с контейнерами и обеспечивает консистентность API.

- **Тесты для динамических контейнеров**:
  - Новый файл `tests/test_services/test_text_client_container.py`:
    - проверка делегирования вызовов к текущему клиенту;
    - проверка корректной замены клиента и вызова `aclose()` у старого;
    - проверка `aclose()` контейнера (закрытие клиента и безопасное поведение после этого);
    - проверка корректной работы при конкурентной генерации и одновременной замене клиента.
  - Новый файл `tests/test_services/test_image_client_container.py`:
    - проверка делегирования всех методов интерфейса к текущему клиенту;
    - проверка корректной замены клиента и вызова `aclose()` у старого;
    - проверка `aclose()` контейнера (закрытие клиента и безопасное поведение после этого);
    - проверка корректной работы при конкурентной генерации и одновременной замене клиента;
    - проверка обработки клиентов без опциональных методов;
    - проверка безопасного поведения при отсутствии клиента;
    - проверка обработки ошибок при закрытии старого клиента;
    - проверка singleton‑функции `get_image_client_container()`.

### Изменено
- **Фабрика текстового клиента**:
  - `services.clients.factory.create_text_client()` теперь инициализирует `GigaChatTextClient` и регистрирует его в singleton‑контейнере `TextClientContainer`, возвращая сам контейнер.
  - Сигнатура и контракт функции не изменились: вызывающий код по‑прежнему получает объект, реализующий `ITextToTextClient`, и может вызывать `generate()`, `set_model()`, `get_available_models()`, `check_api_status()` как раньше.
  - Подготовлена инфраструктура к будущим админ‑командам, способным менять реализацию LLM‑клиента без рестарта бота (через замену инстанса внутри контейнера).

- **Фабрика клиента генерации изображений**:
  - `services.clients.factory.create_image_client()` теперь инициализирует `KandinskyClient` и регистрирует его в singleton‑контейнере `ImageClientContainer`, возвращая сам контейнер.
  - Сигнатура и контракт функции не изменились: вызывающий код по‑прежнему получает объект, реализующий `ITextToImageClient`, и может вызывать `generate()`, `set_model()`, `get_available_models()`, `check_api_status()` как раньше.
  - Подготовлена инфраструктура к будущим админ‑командам, способным менять реализацию TTI‑клиента без рестарта бота (через замену инстанса внутри контейнера).

- **Реализация KandinskyClient**:
  - Метод `set_kandinsky_model()` переименован в `set_model()` для соответствия унифицированному интерфейсу `ITextToImageClient`.
  - Добавлен метод `get_available_models()`, который возвращает список доступных моделей через `check_api_status()` или из `ModelsStore`.
  - Все методы теперь соответствуют расширенному интерфейсу `ITextToImageClient`.

- **Интеграция в сервисы**:
  - `services.image_generator.ImageGenerator` теперь работает с контейнерами для обоих типов клиентов:
    - текстовый клиент создаётся через обновлённую фабрику `create_text_client()`, которая возвращает контейнер `TextClientContainer`;
    - клиент генерации изображений создаётся через обновлённую фабрику `create_image_client()`, которая возвращает контейнер `ImageClientContainer`;
    - доступ к активному клиенту осуществляется через свойство `image_client`, которое возвращает контейнер.
  - Внешнее поведение генерации промптов и существующих команд (`/status`, `/list_models`, `/set_gigachat_model`, `/set_kandinsky_model`) при этом сохраняется.
  - В `services.clients.__init__` добавлены экспорты `TextClientContainer`, `get_text_client_container`, `ImageClientContainer` и `get_image_client_container` для удобного использования контейнеров из других модулей.

- **Обработчики команд**:
  - Команда `/set_kandinsky_model` теперь использует унифицированный метод `set_model()` через контейнер `image_client.set_model()` вместо устаревшего `set_kandinsky_model()`.
  - Все обращения к клиенту генерации изображений выполняются через контейнер, что обеспечивает единообразный подход к работе с обоими типами клиентов.

---

## [6.1.0] 2025-12-2 — Структурированное JSON‑логирование через Loguru, единая обёртка log_event и улучшенная наблюдаемость генераций

### Добавлено
- **Структурированное JSON‑логирование**:
  - В `utils/logger.py` добавлен отдельный sink Loguru с `serialize=True`, пишущий структурированные JSON‑логи в `stdout` c полями `time`, `level`, `message` и всеми дополнительными полями из `logger.bind(...)`.
  - Стандартные текстовые логи для разработки сохранены: человеко‑читаемый вывод в консоль и ротация файлового лога `logs/wednesday_bot.log` (`/app/logs` в Docker, rotation `10 MB`, retention `7 days`).
- **Универсальная обёртка `utils.logger.log_event(...)`**:
  - Новая функция `log_event(event, *, user_id=None, prompt_hash=None, image_id=None, latency_ms=None, status=None, extra=None, level=\"info\", message=None)` для единообразного структурированного логирования.
  - Автоматически фильтрует значения `None`, приводит `user_id` к строке, объединяет стандартные поля (`event`, `user_id`, `prompt_hash`, `image_id`, `latency_ms`, `status`) с `extra` и записывает их через `logger.bind(...)` в JSON‑sink.
  - Уровень логирования задаётся через параметр `level` (`\"trace\" | \"debug\" | \"info\" | \"success\" | \"warning\" | \"error\" | \"critical\"`), при неизвестном значении используется `info`.
  - Добавлен модульный тест `tests/test_utils/test_logger_events.py`, проверяющий формирование корректного JSON (наличие стандартных полей, приведение типов, отсутствие ключей со значением `None`).
- **Структурированные события генерации изображений**:
  - В `services/image_generator.ImageGenerator.generate_frog_image()` и связанных методах добавлены вызовы `log_event(...)` для ключевых этапов: `generation_started`, `generation_caption_selected`, `prompt_selected`, `prompt_registered`, `image_cache_hit`, `image_cache_file_missing`, `image_metadata_saved`, `image_metadata_race_won`, `generation_api_ok`, `generation_attempt`, `generation_attempt_failed`, `generation_attempt_exception`, `generation_exhausted` и др.
  - Во все события передаются типизированные поля: `user_id` (Telegram user id), `prompt_hash`, `image_id` (hash/ID изображения), `latency_ms` (при наличии измерений) и `status` (`ok`, `error`, `cached`, `started`, `reused`, `missing_file`, `redis_unavailable` и т.п.).
  - Логи по circuit breaker Kandinsky (`generation_skipped_circuit_breaker`, `circuit_breaker_check_failed`, `circuit_breaker_record_failure_failed`) теперь тоже структурированы и легко агрегируются по полям статуса и типу ошибки.
- **Prometheus‑метрики и HTTP‑экспортёр `/metrics`**:
  - Добавлен модуль `utils/prometheus_metrics.py` с базовыми метриками генераций:
    - `frog_generations_total{status,source}` — счётчик всех попыток генерации жабы (успехи/ошибки/circuit breaker) с указанием источника (`bot`/`scheduler`).
    - `frog_generation_latency_seconds{status,source}` — гистограмма латентности генераций в секундах с набором бакетов под типичный диапазон (от кэш‑хитов до медленных ответов внешнего API).
    - `frog_generation_queue_length{source}` — gauge для текущей длины очереди задач генерации (если используется явная очередь).
  - В `services/image_generator.ImageGenerator.generate_frog_image()` добавлена интеграция с Prometheus:
    - при кеш‑хите (`image_cache_hit`) и успешной “живой” генерации увеличивается `frog_generations_total{status="success",source="bot"}` и наблюдается `frog_generation_latency_seconds{status="success",source="bot"}` с фактической латентностью;
    - при срабатывании circuit breaker (`generation_skipped_circuit_breaker`) и окончательном провале всех попыток генерации увеличивается `frog_generations_total{status="failure",source="bot"}`.
  - В `main.py` реализован запуск HTTP‑экспортёра Prometheus:
    - конфигурационный параметр `PROMETHEUS_EXPORTER_PORT` добавлен в `utils.config.Config` (`config.prometheus_exporter_port`);
    - вспомогательная функция `_start_prometheus_exporter(...)` поднимает HTTP‑endpoint `/metrics` через `prometheus_client.start_http_server(port)` и логирует события через `log_event` (`prometheus_exporter_started` / `prometheus_exporter_disabled` / `prometheus_exporter_failed`);
    - экспортёр стартует до запуска основного цикла бота, чтобы метрики были доступны сразу.
  - Добавлены unit‑тесты `tests/test_utils/test_prometheus_metrics.py`, проверяющие:
    - инкремент счётчика `frog_generations_total`;
    - работу гистограммы латентности (увеличение счётчика наблюдений);
    - обновление gauge длины очереди;
    - доступность HTTP‑эндпоинта `/metrics` и наличие метрики `frog_generations_total` в ответе.
  - В `docker-compose.yml` и `docker-compose.test.yml` добавлена переменная окружения `PROMETHEUS_EXPORTER_PORT` и проброс порта для сервиса `bot`, что упрощает настройку Prometheus/Grafana в проде и тестовых средах.
- **HTTP healthcheck и интеграция Sentry**:
  - Добавлен отдельный FastAPI‑сервис healthcheck (`/health`) в модуле `services/healthcheck.py`, проверяющий доступность Redis (включая Redis Stream `metrics:events`) и PostgreSQL с агрегированным JSON‑ответом (`status`, `redis`, `postgres`, `queues`, `latency_ms`) и кодом `200` только при полном наборе критичных зависимостей в состоянии `up`, иначе `503`.
  - В `main.py` реализована инициализация `sentry_sdk` через новые настройки `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `RELEASE` (`utils.config.Config`) с интеграциями `AsyncioIntegration` и `FastApiIntegration`, запуск HTTP‑сервера healthcheck в отдельном daemon‑потоке (порт `HEALTHCHECK_PORT`, по умолчанию `8080`) и централизованный репортинг необработанных исключений (`unhandled_exception`) из `main()` и точки входа.
  - В `bot/wednesday_bot.py` добавлен глобальный PTB error handler (`_handle_error`), который логирует полные стеки ошибок, репортит исключения в Sentry и пишет структурированные JSON‑события через `log_event(event="unhandled_exception", status="error", extra={...})` без дублирования обычных логов.
  - В `docker-compose.yml` для сервиса `bot` проброшен порт healthcheck (`HEALTHCHECK_PORT`, по умолчанию `8080`) и добавлен Docker HEALTHCHECK по `http://127.0.0.1:${HEALTHCHECK_PORT}/health`, а в `docker-compose.test.yml` расширено окружение переменными `HEALTHCHECK_PORT` для выравнивания конфигурации с боевым compose.
  - Добавлены юнит‑тесты `tests/test_services/test_healthcheck.py` и `tests/test_utils/test_sentry_integration.py`, проверяющие поведение эндпоинта `/health` при успехе и падении Redis/Postgres, а также корректную инициализацию и отключение Sentry через заглушки `sentry_sdk.init`.


### Изменено
- **Интеграция метрик и логирования**:
  - `utils.metrics.record_metric(...)` по‑прежнему записывает события в Redis Stream `metrics:events` и таблицу `metrics_events`, а сопутствующее логирование теперь дополняется структурированными событиями `log_event(...)` в генераторе изображений.
  - В `ImageGenerator` все места, где ранее использовались только `self.logger.info/warning/error`, для критичных бизнес‑событий дополнены вызовами `log_event(...)`, что обеспечивает согласованный формат логов и облегчает построение дашбордов по полям `user_id`, `prompt_hash`, `image_id`, `latency_ms`, `status`.
  - Интеграция событийной системы метрик (`metrics_events`) и Prometheus:
    - успешные и неуспешные генерации, кеш‑хиты и срабатывания circuit breaker теперь одновременно отражаются в:
      - Postgres‑таблице `metrics_events` (для подробной аналитики и SQL‑отчётов),
      - Prometheus‑метриках (`frog_generations_total`, `frog_generation_latency_seconds`), что позволяет строить Grafana‑дашборды и алерты без дополнительного кода;
    - при ошибках записи метрик в Redis/Postgres или экспорте в Prometheus горячий путь генерации не блокируется (ошибки логируются как best‑effort).
- **Абстракция API‑клиентов и Dependency Injection**:
  - `services.image_generator.ImageGenerator` переведён на DI: вместо прямой работы с HTTP теперь использует абстракции клиентов `ITextToImageClient` и `ITextToTextClient`, а конкретные реализации выбираются через фабрики `services.clients.factory` по ENV (`IMAGE_MODEL_BACKEND`, `TEXT_MODEL_BACKEND`).
  - Вся HTTP‑логика Kandinsky вынесена в `services/clients/kandinsky.py (KandinskyClient)`, где реализованы запросы к `pipelines`, запуск и опрос статуса генерации, а также структурированное JSON‑логирование через Loguru (`logger.bind(event=..., user_id=...)`); бизнес‑логика кеша/метрик и circuit breaker осталась в `ImageGenerator`.
  - **Полное вынесение GigaChat клиента**: `services/clients/gigachat_text.py (GigaChatTextClient)` теперь полностью инкапсулирует всю HTTP‑логику работы с GigaChat API (получение токенов через OAuth2, запросы к `/chat/completions` и `/models`, обработка ошибок и таймаутов) с использованием `aiohttp` вместо синхронного `requests`. Интерфейс `ITextToTextClient` расширен методами `check_api_status()`, `get_available_models()` и `set_model()` для полной заменяемости текстовых моделей. Обработчики в `bot/handlers.py` обновлены для использования `text_client` вместо устаревшего `gigachat_client`, а `ImageGenerator` больше не содержит `gigachat_client` — все операции выполняются через абстракцию `ITextToTextClient`.
  - Добавлены структурные Protocol‑интерфейсы `ITextToImageClient` и `ITextToTextClient` в `services/clients/interfaces.py` и тестовые моки `MockTextToImageClient`/`MockTextToTextClient` в `tests/_doubles/clients.py` (с полной реализацией всех методов интерфейса); тесты `tests/test_services/test_image_generator.py` переписаны под новую архитектуру и используют DI вместо патчинга внутренней HTTP‑логики.

### Откат
- Для возврата к предыдущей схеме логирования достаточно:
  - удалить новый sink с `serialize=True` и функцию `log_event` из `utils/logger.py`;
  - заменить вызовы `log_event(...)` в `services/image_generator.py` и тест `tests/test_utils/test_logger_events.py` на прямые вызовы `logger.info()/warning()/error()` при необходимости.
  - При необходимости отключения Prometheus‑экспортёра достаточно:
    - убрать переменную окружения `PROMETHEUS_EXPORTER_PORT` (или задать неположительное значение) — HTTP‑endpoint `/metrics` не будет запускаться;
    - опционально удалить модуль `utils/prometheus_metrics.py` и связанные тесты, а также удалить зависимость `prometheus_client` из `requirements.txt` и `pyproject.toml`.

---

## [6.0.0] 2025-12-02 — Обновлён CI, улучшена работа с GigaChat-промптами и fallback-механизм, добавлена Redis-интеграция для временного состояния и кэширования, миграция персистентных данных в PostgreSQL завершена, обновлены тесты и инфраструктура, значительно увеличено покрытие тестами, добавлены Docker volumes для файловых операций, нормализация и безопасная запись файлов промптов GigaChat

### Добавлено
- **Расширенное тестовое покрытие**:
  - `tests/test_bot/test_handlers.py` — добавлено 20+ новых тестов для команд:
    - `set_frog_used_command` — тесты успешного выполнения, неверных параметров и отсутствия аргументов
    - `unknown_command` — тест обработки неизвестных команд
    - `admin_add_chat_command` — тесты успешного добавления, отсутствия аргументов и неверного chat_id
    - `admin_remove_chat_command` — тесты успешного удаления и отсутствия аргументов
    - `list_chats_command` — тесты успешного вывода списка и пустого списка чатов
    - `stop_command` — тесты для администраторов и не-администраторов
    - `set_kandinsky_model_command` — тесты успешной установки и отсутствия аргументов
    - `set_gigachat_model_command` — тесты успешной установки, отсутствия клиента и отсутствия аргументов
    - `mod_command` — тесты успешного добавления администратора и отсутствия аргументов
    - `unmod_command` — тесты успешного удаления администратора и отсутствия аргументов
    - `list_mods_command` — тест вывода списка администраторов
    - `list_models_command` — тест вывода списка доступных моделей
  - `tests/test_bot/test_wednesday_bot.py` — добавлено 8 новых тестов:
    - `test_send_error_message` — тест отправки сообщения об ошибке
    - `test_send_user_friendly_error` — тест отправки дружелюбного сообщения об ошибке
    - `test_send_fallback_image_success` — тест успешной отправки fallback изображения
    - `test_send_fallback_image_no_image` — тест отсутствия fallback изображений
    - `test_on_my_chat_member_added` — тест обработки добавления бота в чат
    - `test_on_my_chat_member_removed` — тест обработки удаления бота из чата
    - `test_stop_bot` — тест остановки бота
    - `test_stop_bot_already_stopped` — тест повторной остановки уже остановленного бота
  - `tests/test_bot/test_support_bot.py` — добавлено 4 новых теста:
    - `test_help_command` — тест команды справки
    - `test_start_main_command_non_admin` — тест команды запуска основного бота для не-администратора
    - `test_start_main_command_admin_no_callback` — тест команды запуска без callback функции
    - `test_start_main_command_admin_with_callback` — тест команды запуска с callback функцией
    - `test_log_command_with_args` — тест команды отправки логов с аргументами
  - `tests/test_services/test_image_generator.py` — добавлено 6 новых тестов:
    - `test_get_random_caption` — тест получения случайной подписи
    - `test_get_fallback_prompt` — тест получения fallback промпта
    - `test_get_random_saved_image` — тесты получения случайного сохранённого изображения (с файлами и без)
    - `test_set_kandinsky_model_success` — тест успешной установки модели Kandinsky
    - `test_set_kandinsky_model_not_found` — тест установки несуществующей модели
    - `test_get_auth_headers` — тест получения заголовков авторизации
  - **Новые тестовые файлы для утилит**:
    - `tests/test_utils/test_admins_store.py` — 6 тестов для `AdminsStore`:
      - Добавление администратора (успешное и дубликат)
      - Удаление администратора (успешное и несуществующего)
      - Получение списка администраторов (обычный и полный с главным админом)
    - `tests/test_utils/test_dispatch_registry.py` — 4 теста для `DispatchRegistry`:
      - Проверка отсутствия записи
      - Создание и проверка записи
      - Обработка дубликатов
      - Очистка старых записей
    - `tests/test_utils/test_metrics.py` — 7 тестов для `Metrics`:
      - Инкремент успешных и неудачных генераций
      - Инкремент успешных и неудачных отправок
      - Добавление времени генерации
      - Инкремент срабатываний circuit breaker
      - Получение сводки метрик (пустая и заполненная)
    - `tests/test_utils/test_chats_store.py` — 4 теста для `ChatsStore`:
      - Добавление чата
      - Удаление чата
      - Получение списка чатов (с данными и пустой список)
- **Событийные метрики генераций и кеша в PostgreSQL**:
  - Добавлена таблица `metrics_events` (через `utils.postgres_schema.ensure_schema()` и SQL-миграции `docs/sql/003_add_metrics_events_table*.sql`) для логирования отдельных событий: ошибок, генераций, кеш-хитов/промахов, латентности и статуса.
  - Реализован helper `utils.metrics.record_metric(...)` c типизированным интерфейсом для записи событий и одновременным логированием через Loguru.
  - Добавлены агрегирующие запросы в `utils.metrics` (`get_daily_generation_stats`, `get_top_prompts`) для получения статистики по дням, средней латентности и топу промптов.
  - В `services/image_generator.ImageGenerator.generate_frog_image()` внедрена запись событий: `generation/started`, `generation/ok` с latency и `image_hash`, `cache_hit` с `status='cached'` и `latency_ms=0`, а также событий `error` при сетевых ошибках, срабатывании circuit breaker и полном провале генерации.
  - Обработчики `/frog` и `/force_send` передают `user_id` в генератор, чтобы привязывать события метрик к конкретным пользователям.
  - Запись событий вынесена в Redis Stream `metrics:events` через `record_metric`, а при недоступности Redis предусмотрен fallback на прямую запись в таблицу `metrics_events`, что снижает влияние метрик на latency горячего пути и готовит систему к асинхронным воркерам агрегации.
- **Тесты для `PromptStorage`** (`tests/test_services/test_prompt_generator.py`):
  - Проверка сохранения реального содержимого `"A frog"` без лишних кавычек и пробелов по краям.
  - Проверка корректной записи многострочных промптов с сохранением внутренних переводов строк и пробелов.
  - Проверка, что попытка сохранить пустой промпт приводит к `ValueError` и логируется через warning.
  - Небольшой тест, эмулирующий запись в директорию, ведущую себя как tmpfs‑volume в CI (через временную директорию pytest), для раннего отлова регрессий в файловых операциях с промптами.
- **Интеграционные тесты для команд бота**:
  - `tests/test_bot/test_handlers.py` — добавлены интеграционные тесты `test_status_command_integration_with_postgres_stores` и `test_force_send_command_integration_with_postgres_stores`, использующие реальные async‑сторы PostgreSQL для проверки работы команд `/status` и `/force_send`.
- **CI/CD с поддержкой PostgreSQL и Redis**:
  - `.github/workflows/pytest-check.yml` — добавлены сервисные контейнеры Postgres 16 и Redis 7 для запуска тестов в изолированной среде.
  - Настроены healthchecks для автоматического ожидания готовности БД перед запуском тестов.
  - Добавлена проверка готовности сервисов через Python‑скрипт перед выполнением тестов.
  - Используются безопасные тестовые учетные данные для изолированной CI‑среды.
- **Локальная тестовая инфраструктура**:
  - `docker-compose.test.yml` — отдельный docker-compose файл для тестовой среды с Postgres 16-alpine и Redis 7-alpine.
  - Контейнеры используют `tmpfs` для данных, обеспечивая быструю очистку после тестов и изоляцию от продакшн БД.
  - `Makefile` — разделены команды тестирования: `make test` (только тесты + junit.xml), `make test-cov` (тесты с покрытием + coverage.xml + junit.xml).
  - Команды тестирования автоматически запускают тестовые контейнеры, ждут их готовности, выполняют тесты и очищают контейнеры после завершения.
  - Добавлены вспомогательные команды: `make test-up` (запуск контейнеров), `make test-down` (остановка), `make test-no-containers` (запуск тестов без контейнеров для уже запущенных БД).
- **Боевой запуск через Docker**:
  - `Makefile` — команда `make run` полностью переработана: автоматически очищает и пересобирает Docker-образ бота, поднимает боевые контейнеры Postgres и Redis, ожидает их готовности и запускает бота.
  - Команда `make build` теперь автоматически очищает старый образ перед сборкой нового.
  - Удалены неиспользуемые команды: `run-local`, `init-volumes`, `sync-volumes`.
- **Docker volumes для файловых операций**:
  - `docker-compose.yml` — добавлены именованные тома:
    - `frog_images` → примонтирован в контейнер по пути `/app/data/frogs` для хранения сгенерированных изображений жабы.
    - `logs` → примонтирован в контейнер по пути `/app/logs` для файлов логов бота.
    - `prompt_storage` → примонтирован в контейнер по пути `/app/data/prompts` для файлового хранилища промптов GigaChat.
  - Весь файловый ввод/вывод бота (изображения, логи, промпты) переведён на работу только с этими директориями внутри контейнера.
  - Добавлены рекомендации по резервному копированию томов в `README.md` и `docs/INSTALLATION.md`.
  - Таблица `prompts` используется как каноничное хранилище метаданных промптов (raw/normalized/hash), а файловый `prompt_storage` служит fallback-слоем.
- **PostgreSQL-хранилище промптов**:
  - Добавлена таблица `prompts` (через `utils/postgres_schema.ensure_schema()` и SQL-миграции `docs/sql/001_add_prompts_table*.sql`) с полями `raw_text`, `normalized_text`, `prompt_hash`, `created_at`, `ab_group` и индексом `idx_prompts_prompt_hash`.
  - Реализован репозиторий `utils/prompts_store.PromptsStore` с методами `get_or_create_prompt`, `get_prompt_by_hash`, `get_random_prompt`, нормализующий текст промпта (strip) и считающий sha256‑hash от нормализованного текста.
  - `services/image_generator.ImageGenerator._generate_prompt()` теперь регистрирует все успешные промпты (GigaChat + fallback) в таблице `prompts` и использует БД как основной источник промптов при недоступности GigaChat.
  - Добавлены тесты `tests/test_utils/test_prompts_store.py` и `tests/test_utils/test_prompts_migration_sql.py`, проверяющие корректность схемы, дедупликацию по hash и возможность применения/отката миграций.
- **PostgreSQL-хранилище изображений и content-addressable storage**:
  - Добавлена таблица `images` в `utils/postgres_schema.ensure_schema()` и SQL-миграции `docs/sql/002_add_images_table*.sql` с полями `image_hash`, `prompt_hash` (FK на `prompts.prompt_hash`), `path`, `created_at` и индексом `idx_images_prompt_hash`.
  - Реализован репозиторий `utils/images_store.ImagesStore` c content-addressable схемой: имя файла изображения вычисляется как `sha256(image_bytes).hexdigest()` и используется как ключ `image_hash`, файл хранится как `/app/data/frogs/<image_hash>.png`.
  - Добавлены тесты `tests/test_utils/test_images_store.py` и `tests/test_utils/test_images_migration_sql.py`, покрывающие базовые операции, применение/откат миграций и обработку гонок при параллельной вставке (duplicate key → reuse существующей записи).
  - Внедрён кеш изображений по `prompt_hash` в `services/image_generator.ImageGenerator.generate_frog_image()`: при повторном запросе с тем же нормализованным промптом бот сначала ищет запись в `images` и при наличии использует уже сохранённый файл (cache hit) без обращения к Kandinsky.
  - Логика генерации и сохранения изображений переписана на строгий content-addressable storage‑паттерн: сначала вычисляется `image_hash = sha256(file_bytes).hexdigest()`, затем файл атомарно сохраняется во временный путь и переносится в конечный `/app/data/frogs/<image_hash>.png` без перезаписи уже существующих файлов.
- **Workflow `docker-build.yml`, `Dockerfile`, `.dockerignore`**:
  - Автоматически создаёт Docker image на основе `Dockerfile` и пушит его в GHCR.
- **Логика ленивой загрузки `.env` в `utils/config.py`**:
  - Переменные конфигурации сначала читаются из окружения контейнера (`os.environ`).
  - При отсутствии значения для переменной один раз выполняется fallback через `python-dotenv` без жёстких путей к `.env`.
  - Добавлено логирование ошибок через стандартный `logging` для всех отсутствующих обязательных переменных.
- **Файловое хранилище промптов GigaChat в `services/prompt_generator.py`**:
  - Все успешно сгенерированные промпты GigaChat автоматически сохраняются в директорию `data/prompts/` в виде текстовых файлов.
  - Директория `data/prompts/` создаётся на лету при первом обращении, без необходимости ручной подготовки.
  - Структура хранилища (имена файлов, пометка источника) подготовлена для последующего A/B-тестирования разных вариантов промптов.
- **Файловый fallback-промпт в `services/image_generator.py`**:
  - При любой ошибке GigaChat (таймаут, недоступность API, сетевые проблемы) генератор изображений пробует выбрать случайный промпт из сохранённых файлов `data/prompts/`.
  - Для всех операций добавлено расширенное логирование через `loguru`, а маршруты файлов привязаны к volume‑путям `/app/data/prompts` и `/app/data/frogs` внутри контейнера.

### Изменено

- Система логирования (`utils/logger.py`):
  - ротация логов переведена на размер‑ориентированный режим (`rotation="10 MB"`) с retention `7 days`;
  - все логи пишутся в единый файл `wednesday_bot.log` в директории `logs/` (в Docker — volume `/app/logs`);
  - декоратор `log_execution` теперь автоматически редактирует потенциально чувствительные kwargs
    (ключи, токены, пароли и т.п.) — значения заменяются на `<redacted>`, чтобы предотвратить утечку секретов.
  - **Улучшена система автоматического логирования методов**:
    - Декоратор `@log_execution` теперь поддерживает параметры `level` (DEBUG, INFO, WARNING, ERROR), `log_args` и `log_result` для гибкой настройки логирования отдельных методов.
    - Декоратор `@log_all_methods()` получил новые параметры:
      - `skip_private=True` (по умолчанию) — автоматически исключает приватные методы (начинающиеся с `_`) из логирования, что значительно снижает объём логов от служебных методов.
      - `default_level="INFO"` — уровень логирования по умолчанию для публичных методов.
      - `method_levels` — словарь для явного указания уровня логирования для конкретных методов (например, `{"critical_method": "ERROR"}`).
    - Приватные методы, если они не исключены, автоматически логируются на уровне DEBUG вместо INFO, что позволяет включать их при необходимости без засорения основных логов.
    - Сохранена полная обратная совместимость: существующие использования `@log_all_methods()` работают как раньше, но теперь по умолчанию исключают приватные методы.
- PostgreSQL‑миграции:
  - модуль `utils/postgres_schema.py` получил точку входа `python -m utils.postgres_schema`, позволяющую
    запускать идемпотентную инициализацию схемы через `make migrate` и в CI.
- Инфраструктура тестов и CI:
  - `tests/test_utils/test_images_store.py` и `tests/test_utils/test_prompts_store.py` дополнены явными
    тестами гонок (`asyncio.gather`) для проверки корректности upsert‑логики при параллельной вставке в БД;
  - `Makefile` расширен целями `migrate` и обновлённой целью `ci` (lint → type → migrate → test-cov → build);
  - добавлен workflow `.github/workflows/ci.yml`, выполняющий lint, mypy, миграции, pytest с покрытием
    и сборку Docker‑образа с использованием сервисных контейнеров PostgreSQL и Redis.

### Откат

- **Схема БД**:
  - для отката таблицы `metrics_events` используйте SQL‑скрипт `docs/sql/003_add_metrics_events_table_down.sql`
    (выполнить `DROP TABLE IF EXISTS metrics_events CASCADE;`);
  - для полного возврата к предыдущей схеме можно последовательно выполнить `*_down.sql` миграции в `docs/sql/`.
- **Docker и volumes**:
  - чтобы временно отключить volume‑хранилища, можно убрать тома `frog_images`, `logs`, `prompt_storage`
    из `docker-compose.yml` и вернуть локальные пути в `utils/paths.py` к прежнему виду (до `/app/...`);
  - для удаления всех данных volumes в dev/CI окружении используйте `docker compose down -v`.
- **CI/Makefile**:
  - при необходимости возврата к старому пайплайну достаточно удалить workflow `ci.yml` и вернуть цель `ci`
    в `Makefile` к предыдущей конфигурации (без шагов `migrate` и `build`).
  - Если в файловом хранилище нет ни одного промпта, используется существующий статический fallback на основе `ImageConfig.FROG_PROMPTS`.
  - Добавлено подробное логирование выбора и использования fallback-промптов.
- **Единый Redis‑клиент `utils/redis_client.py`**:
  - Асинхронный клиент `redis.asyncio.Redis` с инициализацией один раз за цикл жизни приложения.
  - Функции `init_redis_pool()`, `get_redis()`, `close_redis()`, `redis_available()` для централизованного доступа.
  - Лёгкий in‑memory fallback с поддержкой TTL, используемый при недоступности Redis.
- **Сервисы Redis‑абстракций**:
  - `services/prompt_cache.py` — кэш промптов (JSON‑совместимых объектов) с TTL и автоматическим fallback.
  - `services/user_state_store.py` — хранилище временного состояния пользователей (JSON‑blob, TTL + очистка).
  - `services/rate_limiter.py` — `RateLimiter` c фиксированным окном и `CircuitBreaker` на базе атомарных операций Redis.
- **Интеграция Redis в ботов и раннер**:
  - `main.py` — при старте пробует инициализировать Redis (по `REDIS_URL` или `REDIS_HOST/PORT/DB/PASSWORD`), при ошибке продолжает работу в деградированном in‑memory режиме.
  - `bot/wednesday_bot.py` — размещает `PromptCache`, `UserStateStore` и `RateLimiter` в `bot_data` для использования обработчиками.
  - `bot/support_bot.py` — добавлен `RateLimiter` для административных команд резервного бота (fail‑open при недоступности Redis).
- **Redis‑основанный circuit breaker для Kandinsky**:
  - `services/image_generator.py` использует `CircuitBreaker` из `services/rate_limiter.py` для подсчёта неудач и окна восстановления поверх Redis.
- **Тесты для Redis‑сервисов**:
  - `tests/test_services/test_redis_services.py` — базовые проверки `PromptCache`, `UserStateStore`, `RateLimiter` и `CircuitBreaker` на in‑memory backend.
 - **PostgreSQL‑клиент и схема БД**:
   - `utils/postgres_client.py` — асинхронный клиент PostgreSQL с одним пулом `asyncpg.Pool` на всё приложение и вспомогательными функциями `init_postgres_pool()`, `get_postgres_pool()`, `close_postgres_pool()`.
   - `utils/postgres_schema.py` — инициализация схемы БД через идемпотентную функцию `ensure_schema()`, создающую необходимые таблицы (`chats`, `admins`, `usage_stats`, `usage_settings`, `dispatch_registry`, `metrics`, `models_kandinsky`, `models_gigachat`).
 - **PostgreSQL‑репозитории вместо JSON‑файлов**:
   - `utils/chats_store.py` — `ChatsStore` переведён на хранение в таблице `chats` (список чатов рассылки).
   - `utils/admins_store.py` — `AdminsStore` использует таблицу `admins` для хранения доп. администраторов (главный по‑прежнему задаётся через `ADMIN_CHAT_ID`).
   - `utils/usage_tracker.py` — `UsageTracker` хранит помесячную статистику в `usage_stats` и настройки лимитов в `usage_settings`.
   - `utils/dispatch_registry.py` — `DispatchRegistry` отслеживает отправки по слотам в таблице `dispatch_registry` вместо `dispatch_registry.json`.
   - `utils/metrics.py` — `Metrics` агрегирует показатели в таблице `metrics` (единая строка `id=1`) вместо `metrics.json`.
   - `utils/models_store.py` — `ModelsStore` разбит на две таблицы: `models_kandinsky` и `models_gigachat` для текущих и доступных моделей.
 - **Документация и запуск**:
   - `README.md` обновлён под новую архитектуру: Postgres‑сторы вместо JSON‑файлов, единый Redis‑клиент и быстрый старт через `docker compose up`.
  - `docs/INSTALLATION.md` переработан: добавлен основной сценарий запуска через `docker-compose` (Postgres + Redis + бот), убраны упоминания JSON‑хранилищ метрик/usage, описаны варианты нативного запуска, добавлено описание Docker volumes для изображений, логов и промптов.
   - `docs/PROJECT_SUMMARY.md` обновлён: разделы по `ChatsStore`, `UsageTracker`, `DispatchRegistry`, `Metrics`, `ModelsStore` переписаны под PostgreSQL, структура `utils/` дополнена `redis_client.py`, `postgres_client.py`, `postgres_schema.py`.
 - **Async-проводка бота и тестов для работы с Postgres**:
   - `bot/wednesday_bot.py` — методы отправки жабы и обработки добавления/удаления чатов теперь используют async‑репозитории (`ChatsStore`, `DispatchRegistry`, `UsageTracker`, `Metrics`, `AdminsStore`) через `await`, без изменения внешнего API.
   - `bot/support_bot.py` — проверки прав администратора и рассылка уведомлений обрабатываются через async‑интерфейс `AdminsStore`.
   - `bot/handlers.py` — все админ‑команды и команды работы с лимитами/чатами/статусом (`/help`, `/frog`, `/status`, `/force_send`, `/add_chat`, `/remove_chat`, `/list_chats` и др.) переведены на использование async‑сторов (`AdminsStore`, `UsageTracker`, `ChatsStore`, `Metrics`) с `await`.
   - `services/image_generator.py` — обновление метрик генерации (`Metrics`) выполняется асинхронно с защитой от сбоев в слое метрик.
   - `tests/conftest.py` — добавлена сессионная async‑фикстура `_setup_test_postgres`, инициализирующая пул `asyncpg`, вызывающая `ensure_schema()` и очищающая основные таблицы перед тестами.
   - `tests/test_utils/test_usage_tracker.py`, `tests/test_utils/test_models_store.py` — переписаны как async‑тесты поверх Postgres‑репозиториев.
   - `tests/test_bot/test_wednesday_bot.py`, `tests/test_bot/test_support_bot.py` — заглушки (`Dummy*Store`, `DummyMetrics`) приведены к async‑интерфейсам, чтобы соответствовать новым async‑сторам.
 - **Расширенное тестовое покрытие**:
   - `tests/test_bot/test_handlers.py` — добавлено 20+ новых тестов для команд:
     - `set_frog_used_command` — тесты успешного выполнения, неверных параметров и отсутствия аргументов
     - `unknown_command` — тест обработки неизвестных команд
     - `admin_add_chat_command` — тесты успешного добавления, отсутствия аргументов и неверного chat_id
     - `admin_remove_chat_command` — тесты успешного удаления и отсутствия аргументов
     - `list_chats_command` — тесты успешного вывода списка и пустого списка чатов
     - `stop_command` — тесты для администраторов и не-администраторов
     - `set_kandinsky_model_command` — тесты успешной установки и отсутствия аргументов
     - `set_gigachat_model_command` — тесты успешной установки, отсутствия клиента и отсутствия аргументов
     - `mod_command` — тесты успешного добавления администратора и отсутствия аргументов
     - `unmod_command` — тесты успешного удаления администратора и отсутствия аргументов
     - `list_mods_command` — тест вывода списка администраторов
     - `list_models_command` — тест вывода списка доступных моделей
   - `tests/test_bot/test_wednesday_bot.py` — добавлено 8 новых тестов:
     - `test_send_error_message` — тест отправки сообщения об ошибке
     - `test_send_user_friendly_error` — тест отправки дружелюбного сообщения об ошибке
     - `test_send_fallback_image_success` — тест успешной отправки fallback изображения
     - `test_send_fallback_image_no_image` — тест отсутствия fallback изображений
     - `test_on_my_chat_member_added` — тест обработки добавления бота в чат
     - `test_on_my_chat_member_removed` — тест обработки удаления бота из чата
     - `test_stop_bot` — тест остановки бота
     - `test_stop_bot_already_stopped` — тест повторной остановки уже остановленного бота
   - `tests/test_bot/test_support_bot.py` — добавлено 4 новых теста:
     - `test_help_command` — тест команды справки
     - `test_start_main_command_non_admin` — тест команды запуска основного бота для не-администратора
     - `test_start_main_command_admin_no_callback` — тест команды запуска без callback функции
     - `test_start_main_command_admin_with_callback` — тест команды запуска с callback функцией
     - `test_log_command_with_args` — тест команды отправки логов с аргументами
   - `tests/test_services/test_image_generator.py` — добавлено 6 новых тестов:
     - `test_get_random_caption` — тест получения случайной подписи
     - `test_get_fallback_prompt` — тест получения fallback промпта
     - `test_get_random_saved_image` — тесты получения случайного сохранённого изображения (с файлами и без)
     - `test_set_kandinsky_model_success` — тест успешной установки модели Kandinsky
     - `test_set_kandinsky_model_not_found` — тест установки несуществующей модели
     - `test_get_auth_headers` — тест получения заголовков авторизации
   - **Новые тестовые файлы для утилит**:
     - `tests/test_utils/test_admins_store.py` — 6 тестов для `AdminsStore`:
       - Добавление администратора (успешное и дубликат)
       - Удаление администратора (успешное и несуществующего)
       - Получение списка администраторов (обычный и полный с главным админом)
     - `tests/test_utils/test_dispatch_registry.py` — 4 теста для `DispatchRegistry`:
       - Проверка отсутствия записи
       - Создание и проверка записи
       - Обработка дубликатов
       - Очистка старых записей
     - `tests/test_utils/test_metrics.py` — 7 тестов для `Metrics`:
       - Инкремент успешных и неудачных генераций
       - Инкремент успешных и неудачных отправок
       - Добавление времени генерации
       - Инкремент срабатываний circuit breaker
       - Получение сводки метрик (пустая и заполненная)
     - `tests/test_utils/test_chats_store.py` — 4 теста для `ChatsStore`:
       - Добавление чата
       - Удаление чата
       - Получение списка чатов (с данными и пустой список)

### Изменено
- **`services/prompt_generator.py` / `PromptStorage`**:
  - Добавлена нормализация промптов перед записью в файловое хранилище: удаляются ведущие и замыкающие пробелы по всему промпту, при этом внутренняя многострочная структура не изменяется.
  - Реализована фильтрация управляющих символов (кроме перевода строки), чтобы в файлы `data/prompts` не попадали невидимые управляющие коды.
  - Логика записи переписана на явное использование `open(..., encoding="utf-8")` и логируется hash содержимого и ожидаемый контейнерный путь `/app/data/prompts/<filename>`.
  - При пустом промпте после нормализации или очистки управляющих символов выбрасывается `ValueError` и пишется предупреждение в логах; вызывающий код обрабатывает ошибку как некритичную.
- **`utils/config.py`**:
  - Обязательные переменные конфигурации (`TELEGRAM_BOT_TOKEN`, `KANDINSKY_API_KEY`, `KANDINSKY_SECRET_KEY`, `CHAT_ID`, `ADMIN_CHAT_ID`) теперь полностью завязаны на переменные окружения контейнера с fallback на локальный `.env`.
  - Опциональные переменные (`GIGACHAT_AUTHORIZATION_KEY`, `SCHEDULER_SEND_TIMES`, `SCHEDULER_WEDNESDAY_DAY`, `SCHEDULER_TZ` и др.) также читаются через единый слой доступа к окружению с поддержкой fallback.
  - Сообщение об ошибке при отсутствии обязательных переменных теперь явно указывает на необходимость проверки окружения контейнера и/или локального `.env`.
  - Функция `_load_dotenv_if_needed()` обёрнута в `try-except` для graceful handling ошибок доступа к `.env` (например, `PermissionError` при отсутствии прав чтения), что позволяет тестам работать без локального `.env` файла.
- **`tests/conftest.py`**:
  - Фикстура `base_env` теперь устанавливает безопасные тестовые значения для Postgres (`test_user`/`test_password_ci_2024`) вместо реальных учетных данных.
  - Добавлены переменные окружения `SCHEDULER_SEND_TIMES`, `SCHEDULER_WEDNESDAY_DAY`, `SCHEDULER_TZ` в `base_env` для предотвращения вызовов `load_dotenv()` при инициализации `SchedulerConfig` во время коллекции тестов.
- **`.github/workflows/pytest-check.yml`**:
  - Убраны хардкод реальных паролей БД из workflow файла; используются безопасные тестовые значения (`test_user`/`test_password_ci_2024`) только для изолированной CI‑среды.
  - Добавлены переменные окружения для Postgres и Redis на уровне job'а для корректной работы тестов в CI.
- **`docker-compose.yml`**:
  - Добавлены healthchecks для Postgres и Redis для контроля готовности сервисов.
  - Сервис `bot` теперь использует только образ `wednesday-bot:local` (без секции `build`), который собирается через `make build`.
  - Добавлены `depends_on` с условиями `service_healthy` для гарантированного запуска бота только после готовности БД.
  - Сервис `bot` переопределяет `POSTGRES_HOST` и `REDIS_HOST` для работы внутри Docker-сети.
- **`Makefile`**:
  - Команда `make test` разделена на две: `make test` (без покрытия, только junit.xml) и `make test-cov` (с покрытием, coverage.xml + junit.xml).
  - Команда `make run` переработана для полного боевого запуска: сборка образа, поднятие БД, ожидание готовности сервисов, запуск бота.
  - Команда `make build` автоматически очищает старый образ перед сборкой нового.
  - Команда `make ci` обновлена: использует `make test-cov` и добавлена проверка форматирования через `make format-check`.
  - Удалены неиспользуемые команды: `run-local`, `init-volumes`, `sync-volumes`.
- **`main.py`**:
  - Удалена жёсткая проверка наличия файла `.env` и любые обращения к `Path(".env")`.
  - `_check_requirements()` больше не зависит от наличия `.env`, а опирается на валидацию и загрузку конфигурации в `utils.config`.
  - Добавлено логирование факта наличия/отсутствия ключевых переменных (`TELEGRAM_BOT_TOKEN`, `KANDINSKY_API_KEY`, `KANDINSKY_SECRET_KEY`, `CHAT_ID`, `ADMIN_CHAT_ID`) при старте бота.
  - Добавлена инициализация пула PostgreSQL (`init_postgres_pool`) и вызов `ensure_schema()` перед запуском ботов; при ошибке подключения к Postgres запуск прерывается.
 - **`services/prompt_generator.py`**:
   - Добавлен класс `PromptStorage` с ответственностью за создание директории `data/prompts/`, сохранение и выбор случайного промпта из файлов.
   - `GigaChatClient` теперь сохраняет каждый успешно сгенерированный промпт в файловое хранилище для дальнейшего анализа и reuse.
 - **`services/image_generator.py`**:
   - Логика генерации промптов через GigaChat вынесена в отдельный слой с явным файловым fallback: при сбое GigaChat используется случайный промпт из `data/prompts/`.
   - Логика построена так, чтобы в будущем было просто подменить стратегию получения промптов (разные A/B-варианты, иные источники), не трогая основной код генерации изображений.
- **`env_example.txt`**:
  - Добавлены переменные `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` для конфигурации Redis.
- **`utils/config.py`**:
  - Добавлены свойства `redis_url`, `redis_host`, `redis_port`, `redis_db`, `redis_password` c дефолтными значениями.
  - Добавлены свойства `postgres_user`, `postgres_password`, `postgres_db`, `postgres_host`, `postgres_port` для конфигурации PostgreSQL с разумными значениями по умолчанию.
- **`services/image_generator.py`**:
  - Встроенный in‑memory circuit‑breaker заменён на Redis‑базированный `CircuitBreaker`, с сохранением минимального локального состояния для обратной совместимости логов.
  - Добавлен слой кеширования изображений по `prompt_hash` поверх таблицы `images`: при повторной генерации с тем же нормализованным промптом бот сначала ищет запись в `images` и при наличии использует уже сохранённый файл (cache hit), а не обращается к Kandinsky.
  - Логика сохранения изображений переписана на content-addressable storage: сначала вычисляется `image_hash = sha256(file_bytes).hexdigest()`, затем файл атомарно сохраняется во временный путь и переносится в конечный `/app/data/frogs/<image_hash>.png` без перезаписи уже существующих файлов.
  - Добавлено подробное логирование этапов генерации и кеширования (start gen, cache hit, save file, db insert, race condition handled, fallback на живую генерацию при потере файла на диске).
- **Тестовая инфраструктура**:
  - `tests/conftest.py` — добавлена фикстура `cleanup_tables` для автоматической очистки таблиц между тестами, обеспечивающая полную изоляцию тестов
  - Все фикстуры для `UsageTracker`, `ModelsStore`, `AdminsStore` теперь полностью асинхронные и корректно работают с PostgreSQL
  - Фикстура `_setup_test_postgres` изменена с `scope="session"` на `scope="function"` для пересоздания пула PostgreSQL в каждом тесте, что решает проблему конфликтов event loop между тестами
  - Добавлены тестовые переменные окружения PostgreSQL в `_session_env_defaults` для принудительного использования тестовых значений независимо от системных переменных
- **Покрытие тестами**:
  - Общее покрытие кода выросло с 43% до 65% (+22 процентных пункта)
  - Добавлено 50+ новых тестов для критичных компонентов бота и утилит
  - Все тесты используют реальные PostgreSQL хранилища для интеграционного тестирования
- **Тестовые заглушки**:
  - `tests/test_bot/test_wednesday_bot.py` — добавлены методы `add_chat` и `remove_chat` в `DummyChatsStore` для корректной работы тестов `on_my_chat_member`
  - Тесты для команд управления администраторами (`mod_command`, `unmod_command`, `list_mods_command`) используют реальный `AdminsStore` с перезагрузкой модуля для обхода патчей в `conftest.py`
- **Docker Compose для тестов**:
  - `docker-compose.test.yml` — удалён устаревший атрибут `version: "3.9"` (совместимо с современными версиями Docker Compose)
- **Конфигурация pytest-asyncio**:
  - `pyproject.toml` — изменён `asyncio_mode` с `"auto"` на `"strict"` для использования одного event loop для всех тестов

### Исправлено
- **`utils/config.py`**:
  - Обработка `PermissionError` и других исключений при загрузке `.env` файла: добавлен `try-except` блок в `_load_dotenv_if_needed()` для graceful fallback, позволяющий тестам работать без локального `.env` файла или при отсутствии прав доступа.
- **`utils/postgres_client.py`**:
  - Исправлена ошибка "Event loop is closed" при закрытии Postgres пула: добавлена проверка состояния event loop перед закрытием пула и обработка `RuntimeError` с проверкой конкретной причины. Улучшено логирование для различения нормального shutdown и реальных ошибок. Ошибки "Event loop is closed" больше не засоряют логи при нормальном завершении приложения.
- **`services/prompt_generator.py`**:
  - Улучшена диагностика аутентификации GigaChat: добавлена проверка наличия `authorization_key` перед использованием, диагностическое логирование (без вывода полного ключа) и улучшено сообщение об ошибке с указанием возможных причин. Теперь легче диагностировать проблемы с настройкой ключа GigaChat.
- **`services/image_generator.py`**:
  - Улучшена обработка ошибок сохранения файлов: добавлена специфичная обработка `PermissionError` (проблемы с правами доступа) и `OSError` (проблемы файловой системы, нехватка места). Улучшены сообщения об ошибках для каждой категории проблем. Добавлен `exc_info=True` для полного стека при неожиданных ошибках. Более понятные сообщения об ошибках сохранения файлов.
- **`bot/handlers.py`**:
  - Исправлена обработка ошибок валидации: исправлен `raise ValueError` без сообщения → теперь с понятным сообщением. Логи теперь содержат понятное сообщение об ошибке валидации.
- **Типизация и стиль кода**:
  - Устранены все ошибки типизации `mypy`: добавлены `await` для всех асинхронных вызовов в `services/prompt_generator.py`, `services/image_generator.py`, `bot/handlers.py`, `bot/wednesday_bot.py`, `bot/support_bot.py`.
  - Исправлены ошибки `ruff` линтинга (`RUF029`, `F821`): добавлены недостающие `await` в тестах, перемещены определения классов внутри функций где необходимо.
  - Исправлены несовместимые типы и присвоения: корректные type hints для `gigachat_ok` и `current_gigachat` в `bot/handlers.py`, правильная обработка `Optional` типов.
- **Безопасность**:
  - Удалён хардкод реальных паролей БД из `.github/workflows/pytest-check.yml` и `tests/conftest.py`; используются безопасные тестовые значения только для изолированной CI‑среды.
- **Тесты**:
  - Исправлена проблема с `PermissionError` при запуске `pytest` из‑за попытки загрузки `.env` во время коллекции тестов: добавлены переменные планировщика в `base_env` фикстуру для предотвращения преждевременной загрузки `.env`.
- **Критические ошибки асинхронности в обработчиках команд**:
  - `bot/handlers.py` — исправлены все отсутствующие `await` для асинхронных вызовов:
    - `usage.increment(1)` → `await usage.increment(1)` (строки 659, 1247)
    - `self.admins_store.is_admin(user_id)` → `await self.admins_store.is_admin(user_id)` (строки 1081, 1640, 1697, 1773, 1828)
    - `self.admins_store.add_admin(user_id)` → `await self.admins_store.add_admin(user_id)` (строка 1666)
    - `self.admins_store.remove_admin(user_id)` → `await self.admins_store.remove_admin(user_id)` (строка 1739)
  - `bot/wednesday_bot.py` — исправлен отсутствующий `await` для `is_dispatched`:
    - `self.dispatch_registry.is_dispatched(...)` → `await self.dispatch_registry.is_dispatched(...)` (строка 292)
  - Устранены ошибки типа `TypeError: 'bool' object can't be awaited` и `RuntimeError: Task <Task pending>`
  - Устранены конфликты корутин при параллельных операциях с Postgres и Redis
- **Проблемы с event loop в тестах**:
  - `utils/postgres_client.py` — добавлена проверка и пересоздание пула PostgreSQL, если он был создан в другом event loop (решает проблему `RuntimeError: Task <Task pending> got Future attached to a different loop`)
  - `tests/conftest.py` — фикстура `_setup_test_postgres` теперь пересоздаёт пул для каждого теста, если он был создан в другом loop, обеспечивая корректную работу с `pytest-asyncio`
  - Исправлена проблема с использованием системных переменных окружения PostgreSQL вместо тестовых значений: добавлены принудительные тестовые значения в `_session_env_defaults`
- **Ошибки в тестах**:
  - Исправлены тесты `test_mod_command_success`, `test_unmod_command_success`, `test_list_mods_command_success` — теперь используют реальный `AdminsStore` с перезагрузкой модуля для корректной работы с PostgreSQL
  - Исправлен тест `test_on_my_chat_member_added` — добавлены методы `add_chat` и `remove_chat` в `DummyChatsStore`
  - Исправлен тест `test_start_main_command_admin_no_callback` — упрощена проверка результата выполнения команды
  - Исправлен тест `test_log_command_with_args` — улучшена работа с временными директориями для логов
- **Ошибки в коде**:
  - `utils/dispatch_registry.py` — исправлена обработка `slot_date` в методе `mark_dispatched`: добавлено преобразование строки в объект `date` через `date.fromisoformat()` для корректной работы с asyncpg (устранена ошибка `DataError: invalid input for query argument $2`)
  - Убран явный каст `$2::date` из SQL запроса, так как asyncpg корректно обрабатывает объекты `date` напрямую

### Поведение и заметки по миграции
- Redis используется только для временного состояния, кэшей и счётчиков: при его недоступности вся критичная бизнес‑логика продолжает работать, опираясь на in‑memory fallback.
- Лимитер `RateLimiter` сознательно настроен в режиме *fail‑open* при ошибках Redis, чтобы инфраструктурные сбои не блокировали пользователей. Для доменов с жёсткими требованиями по лимитам рекомендуется изменить политику на *fail‑closed*.
- Circuit‑breaker для Kandinsky теперь разделяет состояние между инстансами и переживает рестарты, что снижает нагрузку на внешний API при массовых ошибках.

---

## [5.1.0] 2025-11-24 — Реализована функциональность команды /force_send, добавлены pre-commit и pre-push хуки, документация перенесена в /docs

### Добавлено
- **Директория `/docs`**:
  - `PROJECT_SUMMARY.md`, `INSTALLATION.md` и `TYPING_GUIDE.md` перенесены в новую директорию для удобства. Вся документаци будет храниться здесь.
- **Pre-commit и pre-push хуки**:
  - Добавлены соответсвующие хуки для оптимизации разработки.
- **Команда /force_send** (`bot/handlers.py`):
  - Без аргумента: показывает список активных чатов с ID и инструкцию по использованию команды.
  - С аргументом `<chat_id>`: проверяет наличие чата в списке активных, генерирует и отправляет изображение жабы админу и в указанный чат. Если лимит генераций исчерпан, отправляет случайное изображение из архива (`data/frogs`).
  - С аргументом `all`: генерирует и отправляет жабу админу и во все чаты из `chats.json`. Если лимит исчерпан, отправляет случайное изображение из архива во все чаты.
  - Проверка лимита генераций через `UsageTracker.can_use_frog()`.
  - Автоматическое использование fallback-изображений при исчерпании лимита или ошибке генерации.
  - Отправка итогового отчёта о количестве успешных и неудачных отправок.
  - Логирование всех этапов выполнения команды.

### Изменено
- **bot/handlers.py**: полностью переработана функция `admin_force_send_command()` с реализацией полной логики отправки изображений в чаты.

---

## [5.0.0] 2025-11-21 — Добавлен Ruff (lint, format) и улучшенный CI, масштабное улучшение логирования во всём проекте

### Добавлено
- **Централизованная система логирования** (`utils/logger.py`):
  - Декоратор `@log_execution` для автоматического логирования начала, завершения и ошибок функций/методов.
  - Декоратор `@log_all_methods()` для автоматического применения логирования ко всем методам класса.
  - Автоматическое форматирование аргументов функций в логах (исключая `self`/`cls` для читаемости).
  - Поддержка как синхронных, так и асинхронных функций/методов.
  - Автоматическое логирование ошибок с `exc_info=True` для полного стека вызовов.
- **Полное покрытие логированием всех модулей**:
  - `main.py`: логирование всех методов `BotRunner` (инициализация, запуск, остановка, обработка сигналов, очистка ресурсов).
  - `bot/handlers.py`: логирование всех команд и методов `CommandHandlers` (21 метод).
  - `bot/wednesday_bot.py`: логирование всех методов основного бота (инициализация, настройка обработчиков, отправка сообщений, запуск/остановка).
  - `bot/support_bot.py`: логирование всех методов резервного бота (инициализация, команды, запуск/остановка).
  - `services/image_generator.py`: логирование всех методов генератора изображений (генерация, проверка API, работа с моделями).
  - `services/prompt_generator.py`: логирование всех методов клиента GigaChat (получение токенов, генерация промптов, работа с моделями).
  - `services/scheduler.py`: логирование всех методов планировщика задач (планирование, проверка задач, запуск/остановка).
  - `utils/*.py`: логирование всех методов хранилищ и утилит (`ChatsStore`, `AdminsStore`, `UsageTracker`, `Metrics`, `ModelsStore`, `DispatchRegistry`).
- Добавлена полноценная интеграция Ruff.
- Включены расширенные правила (Bugbear, Comprehensions, Annotations и др.).
- Настроены форматирование, сортировка импортов и автоисправление.
- Создан Makefile с едиными командами для разработчиков.
- Добавлен новый reusable workflow GitHub Actions для линтинга.
- Интегрирован Ruff в основной CI-пайплайн.

### Изменено
- **Улучшена детализация логов**:
  - Каждая функция/метод логирует начало выполнения с параметрами.
  - Успешное завершение функций логируется с результатами (где применимо).
  - Все ошибки логируются с полным стеком вызовов через `exc_info=True`.
  - Логирование важных изменений состояния (изменение флагов, сохранение данных, отправка сообщений).
  - Логирование до и после ключевых `await` вызовов в async функциях.
- **Структура логов**:
  - Единый формат логов с указанием функции, параметров и результатов.
  - Исключение служебных параметров (`self`, `cls`) из логов для улучшения читаемости.
  - Автоматическое форматирование сложных объектов (словари, списки) в логах.

### Исправлено
- Исправлен тест `test_generate_prompt_success`: добавлен метод `_clean_prompt` в мок-класс `_DummyGigaChatClient` в `tests/conftest.py` для корректной обработки промптов в тестах.
- Исправлен тест `test_schedule_methods_register_tasks`: согласовано время выполнения задач (`12:00`) и интервал (`60` минут) между регистрацией задач и проверками в тесте.
- Исправлен тест `test_mypy_config_present`: обновлён для проверки конфигурации mypy через секцию `[tool.mypy]` в `pyproject.toml` вместо отдельного файла `mypy.ini`.
- **services/scheduler.py:188**: Исправлена передача аргумента `slot_time` в функцию `send_wednesday_frog` — изменено с keyword argument на positional argument для соответствия сигнатуре функции.
- **tests/test_services/test_prompt_generator.py**: Исправлены ошибки присвоения методов и использования `assert_called_once`:
  - Заменено прямое присвоение `client.session.post = MagicMock(...)` на использование `monkeypatch.setattr()` для корректной типизации.
  - Исправлено использование `assert_called_once()` на объекте типа `Callable` — теперь используется mock-объект напрямую.
  - Обновлены тесты `test_get_access_token_success`, `test_get_access_token_bad_status`, `test_get_access_token_timeout`, `test_generate_prompt_success`.
- **bot/handlers.py:753**: Добавлена проверка на `None` для `status_message` перед вызовом метода `delete()` для предотвращения ошибки `Item "None" of "Message | None" has no attribute "delete"`.
- **bot/wednesday_bot.py:359, 396, 397**: Исправлены несовместимые типы аргументов и присвоений:
  - Исправлено определение `error_details` на строке 351 — убрана запятая в конце, чтобы переменная имела тип `str` вместо `tuple[str]`.
  - Исправлен вызов `_send_admin_error()` — теперь передаётся строка вместо tuple.
  - Исправлен вызов `logger.error()` — теперь передаётся строка вместо tuple.
- **main.py:119**: Исправлен тип аргумента `request_start_main` для `SupportBot`:
  - Функция `request_start_main` теперь объявлена как `async def` для соответствия ожидаемому типу `Callable[[dict[str, Any]], Awaitable[None]]`.

---

## [4.0.0] 2025-11-15

### Добавлено
- Полная типизация проекта с использованием mypy и PEP 484/604:
  - Добавлены аннотации типов во всех модулях: `bot/wednesday_bot.py`, `bot/support_bot.py`, `bot/handlers.py`, `services/image_generator.py`, `services/prompt_generator.py`, `services/scheduler.py`, `utils/*.py`, `main.py`.
  - Создан `mypy.ini` с строгими правилами проверки типов (`disallow_untyped_defs`, `disallow_incomplete_defs`).
  - Добавлены диагностические тесты `tests/test_typing.py` для проверки корректности типизации в CI.
  - Использование современных типов: `Optional`, `Union`, `Callable`, `List`, `Dict`, `Tuple`, `Set`, `Literal`, `Protocol`, `Final`.
  - Типизация Telegram-бота: корректные типы для `Update`, `ContextTypes`, `Message`, `Chat`, `User`.
  - Безопасная работа с Optional: добавлены проверки на `None` для `update.message`, `update.effective_user`, `update.effective_chat` во всех обработчиках.
  - Типизация асинхронных операций: корректные типы для `async def` функций и `Callable[[], Awaitable[None]]`.
  - Типизация хранилищ данных: корректные типы для JSON-хранилищ (`Dict[str, Any]`, `TypedDict` где применимо).
  - Типизация HTTP-клиентов: `aiohttp.ProxyConnector`, `aiohttp.ClientSession` с правильными типами.
  - Вспомогательный метод `ImageGenerator._get_auth_headers()` для безопасного получения заголовков авторизации с проверкой ключей.
- Автоматическая отправка результатов тестов в Codecov при push и PR.
- Каркас автоматических тестов:
  - Структура `tests/` с юнит-тестами для `utils.config`, `services.prompt_generator`, `services.image_generator` и Telegram-обработчиков.
  - `pytest.ini` с настройками запуска и добавлением корня проекта в `PYTHONPATH`.
  - GitHub Actions workflow `.github/workflows/ci.yml` для прогонов тестов и проверки типов при `push`/`pull request`.
- Фикстуры `pytest`:
  - Сессионная фикстура для подстановки обязательных переменных окружения, позволяющая запускать тесты без `.env`.
  - In-memory замены `ModelsStore` и `AdminsStore`, заглушка `GigaChatClient`, моки Telegram-контекста.
- Документация тестов `tests/README.md` с инструкциями по локальному запуску.
- Дополнительные модульные тесты: покрытие ключевых обработчиков (`CommandHandlers`, `WednesdayBot`, `SupportBot`), а также утилит `models_store.py`, `usage_tracker.py` и планировщика задач.

### Изменено
- Типы возвращаемых значений в `utils/config.py`: свойства `telegram_token`, `kandinsky_api_key`, `kandinsky_secret_key`, `chat_id` теперь возвращают `Optional[str]` вместо `str` для корректной типизации.
- Добавлены проверки и assert для обязательных конфигурационных значений при инициализации ботов.
- Улучшена типизация контекста: `on_my_chat_member` теперь использует `ContextTypes.DEFAULT_TYPE` вместо `Any`.
- Все обработчики команд проверяют наличие `update.message` и `update.effective_user` перед использованием.
- `tests/conftest.py` расширен дополнительными фикстурами для валидной инициализации сервисов и очистки окружения между тестами.
- Тесты `test_config_missing_required_env`, `test_prompt_generator`, `test_image_generator` скорректированы для корректной обработки ошибок и моков.
- Workflow CI/CD переработан:
  - Основной workflow `ci.yml` разделён на отдельные job'ы: `type-check` (проверка типов через mypy) и `test` (запуск pytest с покрытием).
  - Добавлена отправка результатов тестов (junit.xml) в Codecov через `codecov/test-results-action@v1`.
  - Настроен полный отчёт о покрытии кода (XML и терминальный формат) с интеграцией в Codecov.

### Исправлено
- Исправлены ошибки типизации: все функции имеют явные аннотации return type и argument type.
- Исправлены несовместимые типы: `str | None` вместо `str` где применимо, удалены возвраты `Any` где возможно.
- Исправлены union-attr ошибки: добавлены проверки на `None` для Optional атрибутов (`update.message`, `status_message`, `next_run`, `self.bot`, и т.д.).
- Исправлены ошибки override сигнатур: все переопределения методов соответствуют сигнатурам родительских классов.
- Исправлены неправильные типы переменных: добавлены явные аннотации для `connector`, `candidates`, `models_list`, `api_models`, `targets`, `chat_id_val`, `pipeline_id`, `uuid_value` и других переменных.
- Исправлены проблемы в `image_generator`:
  - Корректная типизация для `aiohttp.ProxyConnector.from_url()` с использованием `type: ignore[attr-defined]` для совместимости с mypy.
  - Создан метод `_get_auth_headers()` для безопасного получения заголовков авторизации с проверкой ключей API.
  - Добавлено явное приведение к `str` для значений, полученных из API ответов (pipeline_id, uuid) для устранения возврата `Any`.
- Исправлены ошибки `no-redef`: переименованы локальные переменные (`chat_id_val` → `chat_id_error_val`, `model_name` → `matched_model_name`/`selected_model_name`, `pipeline_id` → `selected_pipeline_id`) для избежания конфликтов имён в одной области видимости.
- Исправлены ошибки `method-assign` в тестах: использование `monkeypatch.setattr()` вместо прямого присваивания методов для корректной типизации моков (`test_prompt_generator`, `test_image_generator`).
- Исправлены проблемы с `Generator` фикстурами: добавлены явные типы возврата `Generator[None, None, None]` для всех фикстур в `tests/conftest.py`.
- Исправлена сигнатура `ModelsStore.set_kandinsky_available_models`: теперь поддерживает `List[Dict[str, Any]] | List[str]` для совместимости с тестами.
- Исправлена обработка `last_error` в `CommandHandlers._retry_on_connect_error`: добавлена проверка на `None` перед `raise` для корректной типизации.
- Исправлена типизация `chats_info` в `CommandHandlers.status_command`: изменён тип на `str | int` для поддержки как строковых, так и числовых значений.
- Исправлены проблемы с проверкой `models_data` в `GigaChatClient.get_available_models`: добавлена проверка на `None` перед итерацией.
- Устранены потенциальные ошибки при работе с Optional значениями: добавлены проверки перед вызовом методов (например, `status_message.delete()`, `next_run.weekday()`, `updater.start_polling()`).
- Исключены `ModuleNotFoundError` при запуске `pytest` за счёт добавления `pythonpath = .`.
- Исправлены `AttributeError` в тестах, связанных с моками `ModelsStore`, `GigaChatClient`, `Path.write_bytes`.
- Устранён `ValueError` при повторной инициализации `Config` в teardown благодаря восстановлению переменных окружения в тестах.
- Исправлен `SyntaxWarning` в `tests/conftest.py`: убран `return None` из `finally` блока в фикстуре `reload_config`.

---

## [3.0.0] - 2025-11-11

### Добавлено
- Дополнительная стабилизация сети:
  - Принудительное `http_version: "1.1"` для `HTTPXRequest` у обоих ботов.
  - Warmup `get_me()` и повторная инициализация при `ExtBot is not properly initialized` у `SupportBot`.
- Админ-команды:
  - `/set_frog_limit <threshold>` — установить порог ручных генераций `/frog` (макс. 100, не выше квоты).
  - `/set_frog_used <count>` — установить текущее значение выработки `/frog` за месяц (0..квота).
- Персистентность лимитов в `usage_stats.json`:
  - Теперь файл хранит секцию `settings` с `monthly_quota` и `frog_threshold`.
  - Базовые значения записываются при первом запуске; изменения через команды сохраняются.
- Цепочка переключения SupportBot → основной:
  - SupportBot отправляет “🚀 Запускаю основной бот...”.
  - При своём выключении добавляет строку “🛑 Support Bot остановлен”.
  - После фактического запуска основной редактирует сообщение на “🛑 Support Bot остановлен\n✅ Wednesday Frog Bot запущен”.
- Команда `/stop` (только для админа): полностью останавливает бота с корректным завершением планировщика и polling.
- Резервный бот (поддержка): автоматически запускается при остановке основного бота (по ошибке, сигналу или команде `/stop`).
  - Отвечает на любые неизвестные команды сообщением о техработах.
  - Команда `/log` (только админ): отправляет последний файл логов (и у основного, и у резервного бота).
  - Поддерживает параметр `count`: `/log [count]` — отправляет логи за N дней (1..10). Если аргумент не число — сообщает об ошибке; если больше 10 — ограничивает до 10 и сообщает об ограничении.
  - Команда `/start` (только админ): запускает основной бот и останавливает резервный.
  - При `/stop` финальное сообщение об остановке отправляется также в чат-источник команды.
  - Команда `/help` (только админ): справка по командам резервного бота.
  - При запуске основного через `/start` в резервном боте: отправляется статусное сообщение "🚀 Запускаю...", затем основной бот редактирует его на "✅ Основной бот запущен".
  - При остановке основного через `/stop`: основной бот отправляет "🛑 Останавливаю...", после переключения резервный бот редактирует это сообщение на финальное "🛑 Wednesday Frog Bot остановлен! ...".

### Изменено
- Инфраструктура запуска переработана для взаимного переключения между основным и резервным ботами, исключая одновременную работу на одном токене.
 - По умолчанию при запуске приложения стартует SupportBot; основной включается по команде `/start` от админа.
- Поведение сообщений в админ-чате: только полные сообщения о старте/остановке ботов; редактируемые статусные сообщения не используются.
- Сообщение о старте основного теперь отправляется также в админ-чат (если отличается от `CHAT_ID`) без дублей.
- `/help` основного бота дополнено новыми командами управления лимитами (`/set_frog_limit`, `/set_frog_used`).

### Исправлено
- Улучшена устойчивость к сетевым ошибкам при старте и polling в условиях нестабильного соединения/блокировок.
- Ctrl+C при активном основном боте: супервизор возвращается к SupportBot (флаги остановки сбрасываются), а не завершает приложение.
- /stop в не-админ чатах: после переключения на SupportBot финальное статусное сообщение дополнено строкой о запуске резервного бота.
- Pool timeout при остановке SupportBot: остановка polling выполняется перед отправкой уведомлений админам, добавлена короткая пауза.
- Очистка `pending_*` состояний и флага `_stop_message_sent` предотвращает повторные сообщения об остановке при последовательных /stop и сигналах.
- Финальное сообщение об остановке основного отправляется после остановки polling, чтобы не занимать connection pool.
- Конфликт при остановке `/stop`: добавлена задержка перед запуском резервного бота, чтобы дать PTB завершить финальный `getUpdates` cleanup и избежать `Conflict: terminated by other getUpdates request`.
- Повторная генерация при рестарте в тот же день: привязка слота отправки к ближайшему запланированному времени (а не к текущей минуте), что предотвращает дубликаты после перезапуска благодаря `dispatch_registry`.
- Планировщик больше не выполняет слоты «задним числом» после рестарта: выполнение слота только в окне `[0, CHECK_INTERVAL)` сек после целевого времени. В `send_wednesday_frog` перед генерацией выполняется проверка, что в слоте есть хотя бы один чат без отправки; иначе генерация пропускается.
- Стабилизация переключения на резервного бота: увеличена пауза до 5с перед его запуском и добавлен ретрай `start_polling` при `Conflict`, чтобы гарантировать отсутствие параллельных `getUpdates`.
 - Graceful shutdown: при сигнале во время работы основного — останавливается только основной и автоматически запускается резервный; при сигнале во время работы резервного — завершается приложение полностью.
 - Двойное срабатывание на один Ctrl+C: перед запуском резервного бота сбрасываются флаги остановки (создаётся новый `shutdown_event`, `should_stop=False`), чтобы SupportBot не ловил тот же сигнал.
 - Дублирование финального сообщения при `/stop`: основной бот больше не отправляет своё финальное сообщение, если его уже обязан завершить SupportBot (редактирование статусного сообщения).
 - /help основного бота дополнен описанием команды `/log`.
 - /help резервного бота обновлён с описанием параметра `count` для `/log`.
 - Убрано сообщение "✅ Основной бот запущен" при запуске из SupportBot.
 - Видимость логов SupportBot в терминале: добавлены дополнительные консольные сообщения при старте/остановке.
 - Подробное логирование SupportBot: логируются вызовы команд (/help, /log, /start, unknown), выбранный файл логов и успешная отправка.
 - Финальные сообщения и уведомления:
   - При остановке основного добавлена информация о запуске SupportBot.
   - SupportBot уведомляет админов о своём запуске и остановке.
   - Цепочка сообщений при `/start`: одно сообщение обновляется по шагам.
   - Цепочка сообщений при `/stop`: сначала статус меняется на "Основной бот остановлен", затем добавляется строка о запуске SupportBot.
 - Снижение ошибок cleanup `getUpdates`: уменьшены таймауты connect/read (5с/10с) в обоих ботах, чтобы быстрее завершать очистку при сетевых проблемах.
 - Ошибка `Pool timeout` (HTTPX): увеличен пул соединений до 20 и уменьшён pool timeout до 5с через `HTTPXRequest` в обоих ботах.
 - Исправлена ошибка конфигурации PTB: при использовании `HTTPXRequest` убраны builder-параметры `get_updates_*_timeout` (иначе RuntimeError: "The parameter `connect_timeout` may only be set, if no request instance was set."). Таймауты задаются в `HTTPXRequest`.
 - Надёжный старт при сетевых сбоях: добавлены ретраи запуска (initialize/start) SupportBot с экспоненциальной задержкой; увеличены таймауты HTTPX (connect=15с, read=20с).

### Удалено
- Команда `/set_frog_rate` — признана избыточной.
- Команда `/set_usage_total` — заменена на `/set_frog_used` (корректировка текущей выработки).
- Улучшена устойчивость к сетевым ошибкам при старте и polling в условиях нестабильного соединения/блокировок.
- Ctrl+C при активном основном боте: супервизор возвращается к SupportBot (флаги остановки сбрасываются), а не завершает приложение.
- /stop в не-админ чатах: после переключения на SupportBot финальное статусное сообщение дополнено строкой о запуске резервного бота.
- Pool timeout при остановке SupportBot: остановка polling выполняется перед отправкой уведомлений админам, добавлена короткая пауза.

---

## [2.0.0] - 2025-11-03

### Добавлено
- Генерация промптов через GigaChat с fallback на статические при ошибках.
- Dry-run проверки API:
  - Kandinsky: запрос `/key/api/v1/pipelines` без траты генераций; сохранение списка моделей.
  - GigaChat: получение токена без расхода токенов модели; запрос доступных моделей `GET /api/v1/models`.
- Хранилище моделей `utils/models_store.py` и `data/models.json`:
  - Текущая и доступные модели для Kandinsky и GigaChat.
- Хранилище админов `utils/admins_store.py` и `data/admins.json`.
- Команда `/list_models` (админ): выводит доступные модели обеих систем, отмечает текущие.
- Новые админ-команды: `/force_send`, `/add_chat`, `/remove_chat`, `/list_chats`, `/set_kandinsky_model`, `/set_gigachat_model`, `/mod`, `/unmod`, `/list_mods`.
- Расширенное логирование: подробные debug-логи в dry-run и при сохранении списков моделей.
- Повторные попытки (до 3) при `httpx.ConnectError` для всех команд (отправка сообщений/медиа).

### Изменено
- `/status` доступна только админам и объединяет функциональность старых `/admin_status` и `/health`.
- `/help`: у пользователей убрана информация о логах; показана дата ближайшей авто-отправки. У админов — расширенная справка по новым командам.
- Админ-команды без префикса `admin_` для удобства.
- Метрики: отображаются успешные, всего и процент успеха.
- Убрано ограничение per-user для `/frog` у администраторов.
- Улучшен graceful shutdown: гарантированная отправка финального сообщения перед остановкой компонентов.

### Исправлено
- SSL для GigaChat: поддержка пользовательского сертификата (`GIGACHAT_CERT_PATH`), параметр `GIGACHAT_VERIFY_SSL`.
- Таймауты и обработка сетевых ошибок при запросах к GigaChat (токен/промпт/модели).
- Циклический импорт `utils.config` ↔ `utils.logger` (lazy import).
- Сообщения админам при длинных трассировках: обрезка и отправка короткой версии, защита от `Message is too long`.
- Команда `/status` больше не тратит генерации.

### Удалено
- Команды: `/admin_status`, `/admin_help`, `/health`.

### Технические улучшения
- Логика кэширования и использования сохранённых списков моделей при недоступности API.
- Сохранение не более 30 изображений в `data/frogs` с удалением самых старых.
- Централизованное хранилище конфигураций моделей.

---

## [1.0.0] - 2025-09-01
- Первый релиз бота с генерацией через Kandinsky, планировщиком и базовыми командами `/start`, `/help`, `/frog`.

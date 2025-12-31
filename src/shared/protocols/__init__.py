"""Протоколы для зависимостей сервисов.

Все протоколы организованы по доменам/функциональности в отдельных модулях.
"""

# Infrastructure
# Bot
from shared.protocols.bot import (
    IBotController,
    IChatValidator,
    IHandlersRegistry,
)

# Clients
from shared.protocols.clients import (
    ICaptionProvider,
    ITextToImageClient,
    ITextToTextClient,
)

# Dispatch
from shared.protocols.dispatch import (
    IDataCleanupService,
    IDispatchRegistry,
)
from shared.protocols.infrastructure import (
    ICache,
    ICircuitBreaker,
    IImageStorage,
    ILogger,
    IMetrics,
    IRateLimiter,
)

# Messaging
from shared.protocols.messaging import (
    IFallbackImageProvider,
    IMessagingService,
)

# Queues
from shared.protocols.queues import (
    IIdempotencyService,
    ITaskQueue,
)

# Repositories
from shared.protocols.repositories import (
    IAdminsRepo,
    IChatsRepo,
    IImageRepo,
    IModelsRepo,
    IPromptRepo,
    IUsageTracker,
)

# Services
from shared.protocols.services import (
    IFrogProcessingService,
    IImageService,
)

# Unit of Work
from shared.protocols.uow import (
    ConnectionType,
    IDatabaseUnitOfWork,
    IImageStorageUnitOfWork,
    IUnitOfWorkFactory,
)

__all__ = [
    "IAdminsRepo",
    "IBotController",
    "ICache",
    "ICaptionProvider",
    "IChatsRepo",
    "IChatValidator",
    "ICircuitBreaker",
    "ConnectionType",
    "IDataCleanupService",
    "IDatabaseUnitOfWork",
    "IDispatchRegistry",
    "IFallbackImageProvider",
    "IFrogProcessingService",
    "IHandlersRegistry",
    "IIdempotencyService",
    "IImageRepo",
    "IImageService",
    "IImageStorage",
    "IImageStorageUnitOfWork",
    "ILogger",
    "IMessagingService",
    "IMetrics",
    "IModelsRepo",
    "IPromptRepo",
    "IRateLimiter",
    "ITaskQueue",
    "ITextToImageClient",
    "ITextToTextClient",
    "IUnitOfWorkFactory",
    "IUsageTracker",
]

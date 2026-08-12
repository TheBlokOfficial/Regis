"""Wspólne moduły i narzędzia dla usług Regis."""

from shared.config import ConfigStore, get_service_root
from shared.contracts import (
    CreateLLMProviderRequest,
    HealthResponse,
    LLMProviderDTO,
    LLMProviderListResponse,
    ProviderMetadataResponse,
    ProviderOptionSpec,
    ProviderTypeSpecDTO,
    SelectLLMProviderRequest,
)
from shared.event_bus import Event, EventBus, EventHandler
from shared.logging import get_logger, setup_logging

__version__ = "0.1.0"
__all__ = [
    "ConfigStore",
    "CreateLLMProviderRequest",
    "Event",
    "EventBus",
    "EventHandler",
    "HealthResponse",
    "LLMProviderDTO",
    "LLMProviderListResponse",
    "ProviderMetadataResponse",
    "ProviderOptionSpec",
    "ProviderTypeSpecDTO",
    "SelectLLMProviderRequest",
    "get_logger",
    "get_service_root",
    "setup_logging",
]

"""Konkretni dostawcy STT i logika wyboru. Protokół (`BaseSTTProvider`) zostaje
w `server.ports.stt`, wspólnie dla dostawcy i konsumenta (`server.voice`)."""

from server.ai.stt.factory import STTFactory, STTNotConfiguredError
from server.ai.stt.models import STTInstanceConfig, STTInstanceFileContent, STTProviderType
from server.ai.stt.providers import GroqSTTProvider, MockSTTProvider
from server.ai.stt.registry import STTRegistry
from server.ai.stt.router import STTRouter

__all__ = [
    "GroqSTTProvider",
    "MockSTTProvider",
    "STTFactory",
    "STTInstanceConfig",
    "STTInstanceFileContent",
    "STTNotConfiguredError",
    "STTProviderType",
    "STTRegistry",
    "STTRouter",
]

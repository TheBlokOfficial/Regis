"""Konkretni dostawcy STT i logika wyboru. Protokół (`BaseSTTProvider`) zostaje
w `server.voice.stt` — `voice/` trzyma go dokładnie jak Kernel trzyma
`BaseLLMProvider` (`server.agent.llm`)."""

from server.ai.stt.factory import STTFactory
from server.ai.stt.models import ActiveSTTBackendConfig, STTInstanceConfig, STTInstanceFileContent, STTProviderType
from server.ai.stt.providers import GroqSTTProvider, MockSTTProvider
from server.ai.stt.registry import STTRegistry
from server.ai.stt.router import STTRouter

__all__ = [
    "ActiveSTTBackendConfig",
    "GroqSTTProvider",
    "MockSTTProvider",
    "STTFactory",
    "STTInstanceConfig",
    "STTInstanceFileContent",
    "STTProviderType",
    "STTRegistry",
    "STTRouter",
]

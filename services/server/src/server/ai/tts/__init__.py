"""Konkretni dostawcy TTS i logika wyboru. Protokół (`BaseTTSProvider`) zostaje
w `server.ports.tts`, wspólnie dla dostawcy i konsumenta (`server.voice`)."""

from server.ai.tts.factory import TTSFactory
from server.ai.tts.models import TTSInstanceConfig, TTSInstanceFileContent, TTSProviderType
from server.ai.tts.providers import ElevenLabsTTSProvider, MockTTSProvider
from server.ai.tts.registry import TTSRegistry
from server.ai.tts.router import TTSRouter

__all__ = [
    "ElevenLabsTTSProvider",
    "MockTTSProvider",
    "TTSFactory",
    "TTSInstanceConfig",
    "TTSInstanceFileContent",
    "TTSProviderType",
    "TTSRegistry",
    "TTSRouter",
]

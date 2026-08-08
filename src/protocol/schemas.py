import json
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel

# ─── Modele Konfiguracji Usług (Service Config Schemas) ───────────────────

class SatelliteConfig(BaseModel):
    """Oficjalny schemat kontraktu konfiguracyjnego Satelity."""
    wakeword_threshold: float = 0.65
    silence_timeout_ms: int = 1500

class OllamaWorkerConfig(BaseModel):
    """Schemat kontraktu konfiguracyjnego usługi Ollama Worker."""
    model_name: str = "qwen3.5:9b"

class STTConfig(BaseModel):
    """Schemat kontraktu konfiguracyjnego usługi STT Worker (Whisper)."""
    stt_model_size: str = "small"
    stt_language: str = "pl"

class TTSConfig(BaseModel):
    """Schemat kontraktu konfiguracyjnego usługi TTS Worker (Piper)."""
    tts_model_name: str = "pl_PL-darkman-medium"

# Aliasy wstecznej kompatybilności
LLMConfig = OllamaWorkerConfig
WorkerConfig = OllamaWorkerConfig
AudioConfig = STTConfig
SpeechConfig = STTConfig


class ClientServicesConfig(BaseModel):
    """Oficjalny, silnie typowany zagregowany zestaw konfiguracji usług Klienta."""
    satellite: SatelliteConfig | None = None
    stt_worker: STTConfig | None = None
    tts_worker: TTSConfig | None = None
    ollama_worker: OllamaWorkerConfig | None = None

# Alias wstecznej kompatybilności
NodeServicesConfig = ClientServicesConfig


class ToolExecutionRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy do proxy narzędzi w Kontrolerze."""
    tool_name: str
    arguments: dict
    room: str | None = None


class ClientRegistrationRequest(BaseModel):
    """Payload wysyłany przez Aplikację Kliencką podczas rejestracji w Kontrolerze."""
    id: str
    name: str | None = None
    host: str
    # Słownik usług: np. {"ollama_worker": {...}, "stt_worker": {...}, "tts_worker": {...}, "satellite": {...}}
    services: dict[str, dict] = {}


# Aliasy wstecznej kompatybilności ze starym nazewnictwem "Node":
NodeRegistrationRequest = ClientRegistrationRequest


class ClientConfigRequest(BaseModel):
    """Payload aktualizacji konfiguracji Klienta z poziomu Kontrolera / Web UI."""
    name: str | None = None
    room: str | None = None
    services: dict[str, dict] | None = None

NodeConfigRequest = ClientConfigRequest


# ─── Modele Komunikatów i Stanów Mikrousług ───────────────────────────────

class ServiceState(str, Enum):
    """Oficjalny, znormalizowany stan operacyjny mikrousługi w kontrakcie sieciowym Regis."""
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    BUSY = "BUSY"


class ServiceName(str, Enum):
    """Oficjalny wykaz nazw usług w systemie Regis."""
    SATELLITE = "satellite"
    STT_WORKER = "stt_worker"
    TTS_WORKER = "tts_worker"
    OLLAMA_WORKER = "ollama_worker"


class SatelliteAction(str, Enum):
    """Oficjalny spis dopuszczalnych akcji dla Satelity."""
    RESUME = "resume"
    PAUSE = "pause"


ServiceAction = SatelliteAction


class ServiceCommand(str, Enum):
    """Oficjalny spis komend domenowych przesyłanych z Kontrolera do usług."""
    PLAY_AUDIO = "play_audio"
    SATELLITE_CONTROL = "satellite_control"
    CHAT_STREAM = "chat_stream"


class WSCommand(BaseModel):
    """Komenda przesyłana z Kontrolera do Klienta przez WebSocket."""
    command: str
    data: dict[str, Any] = {}


class WSCommandResult(BaseModel):
    """Odpowiedź wysyłana z Klienta do Kontrolera z wynikiem wykonanej komendy."""
    type: Literal["command_result"] = "command_result"
    command: str
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class WSClientEvent(BaseModel):
    """Zdarzenie z Aplikacji Klienckiej (np. VAD, Audio) przesyłane do Kontrolera."""
    type: Literal["satellite_event"] = "satellite_event"
    event_type: str
    data: dict[str, Any] = {}


# Alias wstecznej kompatybilności
WSSatelliteEvent = WSClientEvent

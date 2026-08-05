import json
from pydantic import BaseModel

# ─── Modele Rejestru Encji ─────────────────────────────────────────────────

from typing import Literal

class CloudProviderConfig(BaseModel):
    """Konfiguracja providera chmurowego (np. OpenRouter, Groq)."""
    id: str
    type: str  # np. "openrouter"
    api_key: str
    model: str
    mode: Literal["basic", "extended"] = "extended"
    priority: int = 50

# ─── Modele Konfiguracji Usług (Service Config Schemas) ───────────────────

class SatelliteConfig(BaseModel):
    """Oficjalny schemat kontraktu konfiguracyjnego Satelity (Audio/VAD/Wakeword)."""
    internal_proxy_url: str = "http://127.0.0.1:47831"
    capabilities: list[str] = ["audio_input", "tts_output", "wakeword"]
    wakeword_local: bool = True
    wakeword_threshold: float = 0.65
    silence_timeout_ms: int = 1500

class LLMConfig(BaseModel):
    """Schemat kontraktu konfiguracyjnego usługi LLM."""
    model_name: str = "qwen3.5:9b"
    port: int = 8001
    priority: int = 100
    controller_url: str | None = None
    mode: Literal["basic", "extended"] = "extended"

class AudioConfig(BaseModel):
    """Schemat kontraktu konfiguracyjnego usługi Audio (STT + TTS)."""
    stt_model_size: str = "small"
    stt_language: str = "pl"
    tts_model_name: str = "pl_PL-darkman-medium"
    port: int = 8002

class STTConfig(AudioConfig):
    pass

class TTSConfig(AudioConfig):
    pass

# Alias wstecznej kompatybilności dla starego Workera
WorkerConfig = LLMConfig


class NodeServicesConfig(BaseModel):
    """Oficjalny, silnie typowany zagregowany zestaw konfiguracji usług dla Węzła Klienta."""
    satellite: SatelliteConfig | None = None
    audio: AudioConfig | None = None
    llm: LLMConfig | None = None


class WorkerRegistrationRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy podczas rejestracji w Kontrolerze."""
    id: str
    host: str
    port: int
    model_name: str
    priority: int = 100
    mode: Literal["basic", "extended"] = "extended"


class ToolExecutionRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy do proxy narzędzi w Kontrolerze."""
    tool_name: str
    arguments: dict
    room: str | None = None


class SatelliteRegistrationRequest(BaseModel):
    """Payload wysyłany przez Satelitę podczas rejestracji w Kontrolerze."""
    id: str
    room: str | None = None
    type: str
    capabilities: list[str]
    wakeword_local: bool = False


class ClientRegistrationRequest(BaseModel):
    """Payload wysyłany przez Aplikację Kliencką podczas rejestracji w Kontrolerze."""

    id: str
    name: str | None = None
    host: str
    port: int | None = None
    # Słownik usług: np. {"llm": {...}, "audio": {...}, "satellite": {...}}
    services: dict[str, dict] | list[str] = {}

    # Opcjonalne pola spłaszczone (dla kompatybilności ze starymi żądaniami)
    model_name: str | None = None
    priority: int = 100
    room: str | None = None
    node_type: str = "desktop"
    capabilities: list[str] = ["audio_input", "tts_output", "wakeword"]
    wakeword_local: bool = True

    def get_normalized_services(self) -> dict[str, dict]:
        """Zwraca spójny słownik usług {"service_name": {metadane_usługi}}."""
        if isinstance(self.services, dict) and self.services:
            return self.services

        normalized = {}
        service_list = self.services if isinstance(self.services, list) else ["llm", "audio", "satellite"]
        if "llm" in service_list or "worker" in service_list:
            normalized["llm"] = {
                "model_name": self.model_name or "qwen3.5:9b",
                "priority": self.priority,
                "mode": "extended",
                "port": 8001
            }
        if "audio" in service_list or "stt" in service_list or "tts" in service_list or "worker" in service_list:
            normalized["audio"] = {
                "stt_model_size": "small",
                "stt_language": "pl",
                "tts_model_name": "pl_PL-darkman-medium",
                "port": 8002
            }
        if "satellite" in service_list:
            normalized["satellite"] = {
                "room": self.room,
                "node_type": self.node_type,
                "capabilities": self.capabilities,
                "wakeword_local": self.wakeword_local,
            }
        return normalized


# Aliasy wstecznej kompatybilności ze starym nazewnictwem "Node":
NodeRegistrationRequest = ClientRegistrationRequest


SUPPORTED_REGIS_MODELS = [
    {
        "id": "qwen3.5:9b",
        "name": "Regis Agent (Qwen 3.5 9B)",
        "description": "Oficjalny, zalecany model produkcyjny z pełnym rozumowaniem ReAct.",
        "default": True,
    },
    {
        "id": "qwen2.5:3b",
        "name": "Light Agent (Qwen 2.5 3B)",
        "description": "Szybki, lżejszy agent dla średnich komputera.",
        "default": False,
    },
    {
        "id": "qwen2.5:0.5b",
        "name": "Butler NLU (Qwen 2.5 0.5B)",
        "description": "Kompaktowy parser komend dla słabych urządzeń.",
        "default": False,
    },
]


class ClientConfigRequest(BaseModel):
    """Payload aktualizacji konfiguracji Klienta z poziomu Kontrolera / Web UI."""
    name: str | None = None
    services: NodeServicesConfig | dict[str, dict] = {}


NodeConfigRequest = ClientConfigRequest


# ─── Modele Komunikatów WebSocket ──────────────────────────────────────────

from typing import Any

from enum import Enum

class ServiceAction(str, Enum):
    """Oficjalny spis dopuszczalnych akcji na usługach Węzła."""
    RESUME = "resume"
    PAUSE = "pause"


class ServiceCommand(str, Enum):
    """Oficjalny spis dopuszczalnych komend sieciowych (SSE) dla usług."""
    PLAY_AUDIO = "play_audio"
    SERVICE_CONTROL = "service_control"


class ServiceControlPayload(BaseModel):
    """Payload dla komendy 'service_control'."""
    service: str
    action: ServiceAction


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


class WSSatelliteEvent(BaseModel):
    """Zdarzenie z Satelity (np. VAD, Audio) przesyłane z Klienta do Kontrolera."""
    type: Literal["satellite_event"] = "satellite_event"
    event_type: str
    data: dict[str, Any] = {}

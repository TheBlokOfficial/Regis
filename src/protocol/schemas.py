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


class WorkerRegistrationRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy podczas rejestracji w Kontrolerze."""
    id: str
    host: str
    port: int
    model_name: str
    priority: int = 100  # Wyższa wartość = wyższa ważność (100 = GPU PC, 50 = OpenRouter cloud, 10 = RPi fallback)
    mode: Literal["basic", "extended"] = "extended"


class ToolExecutionRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy do proxy narzędzi w Kontrolerze."""
    tool_name: str
    arguments: dict
    room: str | None = None  # kontekst pokoju Satelity — propagowany przez cały stos


class SatelliteRegistrationRequest(BaseModel):
    """Payload wysyłany przez Satelitę podczas rejestracji w Kontrolerze."""
    id: str
    room: str | None = None      # np. "salon", "sypialnia" lub None (bez filtrowania)
    type: str                     # "terminal" | "desktop" | "esp32"
    capabilities: list[str]      # np. ["text"] lub ["audio_in", "audio_out"]
    wakeword_local: bool = False


class ClientRegistrationRequest(BaseModel):
    """Payload wysyłany przez Aplikację Kliencką podczas rejestracji w Kontrolerze."""

    id: str
    name: str | None = None
    host: str
    port: int | None = None
    # Słownik usług: {"worker": {"model_name": "..."}, "satellite": {"room": "..."}} lub lista dla wstecznej kompatybilności
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
        service_list = self.services if isinstance(self.services, list) else ["worker", "satellite"]
        if "worker" in service_list:
            normalized["worker"] = {
                "model_name": self.model_name,
                "priority": self.priority,
                "mode": "extended"
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
    services: dict[str, dict] = {}


NodeConfigRequest = ClientConfigRequest


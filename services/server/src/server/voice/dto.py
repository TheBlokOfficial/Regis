"""DTO warstwy REST domeny Voice — prywatne słownictwo, nie w `shared/contracts.py`
(mirror `world/dto.py`). `STTProviderDTO`/`TTSProviderDTO` i towarzysze to 1:1
kształt `LLMProviderDTO`/`LLMProviderListResponse`/`CreateLLMProviderRequest`/
`SelectLLMProviderRequest` (`shared/contracts.py`) — nie generalizowane do
wspólnego kontraktu (ryzyko dotknięcia działającego kodu LLM bez potrzeby),
tylko domenowo nazwane pod Voice, mirror istniejącego tu wzorca."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class STTProviderDTO(BaseModel):
    """Reprezentacja instancji dostawcy STT dla API. Mirror `shared.LLMProviderDTO`."""

    id: str = Field(..., description="Unikalne ID instancji backendu STT (np. stt_groq_default)")
    type: str = Field(..., description="Typ dostawcy (GROQ)")
    name: str = Field(..., description="Wyświetlana nazwa")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje konfiguracyjne")
    is_active: bool = Field(default=False, description="Czy ten dostawca jest obecnie aktywny")


class STTProviderListResponse(BaseModel):
    """Odpowiedź dla GET /api/v1/voice/stt/providers."""

    providers: list[STTProviderDTO] = Field(default_factory=list, description="Lista dostępnych dostawców STT")
    active_id: str = Field(..., description="ID obecnie aktywnego dostawcy STT")


class SelectSTTProviderRequest(BaseModel):
    """Żądanie dla PUT /api/v1/voice/stt/providers/active."""

    provider_id: str = Field(..., description="ID dostawcy STT do aktywacji")


class UpdateProviderRequest(BaseModel):
    """Żądanie dla PUT /api/v1/voice/{stt,tts}/providers/{id} — edycja istniejącej instancji.

    Wspólne dla STT i TTS (identyczny kształt, zero pól specyficznych dla typu), mirror
    `shared.contracts.UpdateLLMProviderRequest`. Typ jest niezmienny — jego zmiana
    unieważniłaby wszystkie opcje. Pominięte pole sekretne zachowuje obecną wartość.
    """

    name: str | None = Field(default=None, description="Nowa nazwa; pominięta zachowuje obecną")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje do nadpisania")


class CreateSTTProviderRequest(BaseModel):
    """Żądanie dla POST /api/v1/voice/stt/providers."""

    type: str = Field(..., description="Typ dostawcy (GROQ)")
    name: str = Field(..., description="Wyświetlana nazwa")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje konfiguracyjne")
    custom_id: str | None = Field(default=None, description="Opcjonalne własne ID")


class TTSProviderDTO(BaseModel):
    """Reprezentacja instancji dostawcy TTS dla API. Mirror `shared.LLMProviderDTO`."""

    id: str = Field(..., description="Unikalne ID instancji backendu TTS (np. tts_elevenlabs_default)")
    type: str = Field(..., description="Typ dostawcy (ELEVENLABS)")
    name: str = Field(..., description="Wyświetlana nazwa")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje konfiguracyjne")
    is_active: bool = Field(default=False, description="Czy ten dostawca jest obecnie aktywny")


class TTSProviderListResponse(BaseModel):
    """Odpowiedź dla GET /api/v1/voice/tts/providers."""

    providers: list[TTSProviderDTO] = Field(default_factory=list, description="Lista dostępnych dostawców TTS")
    active_id: str = Field(..., description="ID obecnie aktywnego dostawcy TTS")


class SelectTTSProviderRequest(BaseModel):
    """Żądanie dla PUT /api/v1/voice/tts/providers/active."""

    provider_id: str = Field(..., description="ID dostawcy TTS do aktywacji")


class CreateTTSProviderRequest(BaseModel):
    """Żądanie dla POST /api/v1/voice/tts/providers."""

    type: str = Field(..., description="Typ dostawcy (ELEVENLABS)")
    name: str = Field(..., description="Wyświetlana nazwa")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje konfiguracyjne")
    custom_id: str | None = Field(default=None, description="Opcjonalne własne ID")

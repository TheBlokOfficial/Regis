"""Wspólny kształt zawartości pliku instancji dostawcy AI — LLM, STT, TTS.

Trzy domeny deklarowały te same dwa pola (`name`, `options`) w trzech miejscach, a
`ProviderRegistry` znał je wyłącznie jako `BaseModel` — czyli nie wiedział o nich nic.
Wystarczyło to, dopóki rejestr tylko przenosił zawartość między dyskiem a fabryką;
odkąd **rozwiązuje w niej referencje sekretów** (`build_provider()`), musi widzieć worek
opcji w typach, a nie przez `getattr`.

Pole `type` zostaje w domenach: każda ma własny enum (`ProviderType`, `STTProviderType`,
`TTSProviderType`) i ich scalenie byłoby udawaniem, że dostawca LLM i dostawca TTS są
tym samym bytem.
"""

from typing import Any

from pydantic import BaseModel, Field


class ProviderInstanceContent(BaseModel):
    """Część zawartości pliku instancji wspólna dla wszystkich dostawców AI."""

    name: str = Field(description="Wyświetlana nazwa instancji")
    options: dict[str, Any] = Field(default_factory=dict, description="Worek z opcjami specyficznymi dla dostawcy")

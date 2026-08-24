"""Porty — kontrakty dostawców AI, których konkretne implementacje żyją w `server.ai`.

Dlaczego osobny pakiet, skoro protokół zwykle mieszka u swojego właściciela?
Bo tutaj właściciel jest **dwóch stron naraz**: `BaseLLMProvider` opisuje, czego
potrzebuje kernel (`server.agent`), a implementują go konkrety z `server.ai` —
i dopóki protokół mieszkał u konsumenta, `server.ai` musiało importować z powrotem
`server.agent`/`server.voice`. Powstawały dwa cykle między pakietami, utrzymywane
przy życiu leniwymi importami w ciele funkcji (`agent/engine.py` opisywał to
wprost: „modułowy import tworzył cykl, który wywracał się przy każdej kolejności
importów zaczynającej się od `server.ai`"). Leniwy import przenosi błąd z czasu
importu na czas wykonania i uniemożliwia statyczną weryfikację granicy — to
obejście, nie rozwiązanie.

Dziś kierunek jest jednokierunkowy i weryfikowalny grep-em:

```text
    agent/  ─┐
    voice/  ─┼──> ports/ <──  ai/
    world/  ─┘
```

**Reguła przynależności**: do `ports/` trafia kontrakt, którego konkrety mieszkają
w `server.ai` (LLM, STT, TTS, wake-word). `WorldInterface` **zostaje** w
`agent/context_provider.py` — implementuje go `server.world`, a `world -> agent`
jest jednokierunkowe, więc żaden cykl tam nie powstał i decyzja z
`docs/manifest.md` („kernel jest właścicielem tego protokołu") obowiązuje dalej.
Port przenosi się tu dopiero, gdy realnie zaczyna wiązać dwie strony — nie
z wyprzedzenia.
"""

from server.ports.llm import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    LLMRole,
    ReasoningChunk,
    ToolCallRequest,
    ToolDefinition,
    ToolResult,
)
from server.ports.stt import BaseSTTProvider
from server.ports.tts import BaseTTSProvider
from server.ports.wakeword import WakeWordDetector

__all__ = [
    "BaseLLMProvider",
    "BaseSTTProvider",
    "BaseTTSProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMRole",
    "ReasoningChunk",
    "ToolCallRequest",
    "ToolDefinition",
    "ToolResult",
    "WakeWordDetector",
]

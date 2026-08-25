"""Obserwator wywołań LLM — zrzut tego, co naprawdę poleciało do modelu.

Warstwa konkretna, składana w `main.py`, dokładnie tak jak `server.ai`: implementuje
`BaseLLMProvider` z `server.ports`, a kernel nigdy jej nie zna z nazwy. Powstała,
bo dwie najważniejsze części promptu są z natury ulotne — dynamiczny `system_prompt`
budowany przez silnik świata co turę i `turn_context`, który nigdy nie trafia do
pamięci sesji. Bez zrzutu w momencie wywołania nie da się ich odtworzyć z niczego.

**Kierunek zależności.** `telemetry -> ai` (po `LLMAttempt`), `telemetry -> ports`,
`telemetry -> shared`. Krawędź do `ai` jest jednokierunkowa i świadoma: sekwencja
prób łańcucha fallbacku istnieje wyłącznie w `LLMRouter`, więc obserwator tej
sekwencji musi mówić jej słownictwem. Odwrotnie nie wolno — `ai` i `agent` nie
importują `telemetry`:

```bash
grep -rn "from server.telemetry" services/server/src/server/agent/ services/server/src/server/ai/
```
(poprawny wynik: brak trafień)
"""

from server.telemetry.models import GenerationRecord
from server.telemetry.recorder import RecordingLLMProvider, TurnAttemptCollector
from server.telemetry.store import GenerationLogStore

__all__ = [
    "GenerationLogStore",
    "GenerationRecord",
    "RecordingLLMProvider",
    "TurnAttemptCollector",
]

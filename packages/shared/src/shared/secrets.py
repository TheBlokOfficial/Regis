"""Referencje do sekretów: wartość opcji może być literałem albo wskazaniem `env:NAZWA`.

**Dlaczego nie zwykła migracja kluczy do `.env`.** Klucze API nie leżą w repozytorium
(`.gitignore` blokuje `data/`), więc problemem nie jest wyciek, tylko brak sposobu na
wstrzyknięcie klucza do kontenera bez ręcznej edycji JSON-a w wolumenie. Zarazem
dostawcy są **wielo-instancyjni** — „Groq (kontakt@)" i „Groq (zapasowy)" to dwa presety
z osobnymi kluczami, zarządzane CRUD-em z Web UI. Jedna zmienna `GROQ_API_KEY` nie ma
w tym modelu sensu; wiązanie musi zostać przy instancji.

Stąd **pośrednictwo zamiast migracji**: w polu klucza wpisuje się `env:REGIS_GROQ_KONTAKT`,
a wartość przychodzi ze środowiska w chwili budowy dostawcy. Istniejące literały działają
dalej bez żadnej zmiany — nie ma momentu przełączenia i nie ma czego migrować.

Prefiks jest jednoznaczny, więc rozwiązywanie **nie potrzebuje wiedzy o tym, które pole
jest sekretne**. Dzięki temu jedna funkcja obsługuje worek opcji dowolnego dostawcy,
a rozwiązywanie mieści się w dwóch punktach na granicy budowy konkretu:
`ProviderRegistry.build_provider()` (LLM/STT/TTS) i `WorldEngine._build_client()` (token
Home Assistant).

Referencja **nie jest sekretem** — to nazwa zmiennej. Maskowanie w warstwie REST
(`ai/provider_crud.py`, `world/api/mappers.py`) celowo ją przepuszcza, żeby użytkownik
widział w formularzu, skąd klucz pochodzi, zamiast rzędu kropek.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from shared.logging import get_logger

logger = get_logger("regis.shared.secrets")

SECRET_REF_PREFIX = "env:"
"""Prefiks wskazujący, że wartość jest NAZWĄ zmiennej środowiskowej, nie samym sekretem."""


def is_secret_ref(value: Any) -> bool:
    """Czy wartość jest referencją `env:NAZWA` (a nie literalnym sekretem)."""
    return isinstance(value, str) and value.strip().startswith(SECRET_REF_PREFIX)


def resolve_secret(value: Any, field_name: str = "wartość") -> Any:
    """Zamienia referencję `env:NAZWA` na zawartość zmiennej; literały zwraca bez zmian.

    Brak zmiennej kończy się **pustym stringiem i błędem w logu**, nie wyjątkiem — to ta
    sama łagodna degradacja co przy pustym kluczu wpisanym ręcznie: dostawca odrzuci
    żądanie, a przyczyna będzie widoczna w zakładce Logi. Wywrócenie startu serwera przez
    jedną źle skonfigurowaną instancję dostawcy (spośród kilku, z których aktywna jest
    jedna) byłoby lekarstwem gorszym od choroby.
    """
    if not is_secret_ref(value):
        return value
    variable = value.strip()[len(SECRET_REF_PREFIX) :].strip()
    if not variable:
        logger.error(f"Pusta nazwa zmiennej w referencji '{field_name}' — oczekiwano 'env:NAZWA'.")
        return ""
    resolved = os.environ.get(variable)
    if resolved is None:
        logger.error(
            f"Referencja '{field_name}' wskazuje na zmienną środowiskową [{variable}], "
            f"której nie ma w środowisku. Dostawca dostanie pustą wartość."
        )
        return ""
    return resolved


def resolve_secret_refs(options: Mapping[str, Any]) -> dict[str, Any]:
    """Kopia worka opcji z rozwiniętymi referencjami — wołana tuż przed budową dostawcy.

    Zwraca **nowy** słownik: rozwiązana postać nie może wrócić do magazynu ani wyciec
    przez REST, więc nigdy nie mutujemy oryginału.
    """
    return {key: resolve_secret(value, field_name=key) for key, value in options.items()}

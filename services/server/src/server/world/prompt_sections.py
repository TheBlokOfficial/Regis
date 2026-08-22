"""Edytowalne sekcje kontekstu tury — tekst, który agent dostaje o świecie.

Do tej pory wszystkie te zdania były literałami w `world/engine.py`, więc
zmiana instrukcji typu "odpowiadaj krótko, bo to pójdzie na głos" wymagała
edycji kodu źródłowego. Tutaj mieszkają jako konfiguracja z wartościami
domyślnymi (dokładnie dawny tekst) i nadpisaniami zapisywanymi z Web UI.

**Granica edytowalności — świadoma:** użytkownik edytuje to, co agent ma
*usłyszeć*; silnik renderuje *dane*. Format wiersza urządzenia
(`- [entity_id] Nazwa (możliwości: …)`) i nagłówki pokoi zostają w kodzie —
zepsuty szablon wiersza po cichu zamieniłby całą listę urządzeń w śmieci, a
to nie jest tekst, który ktokolwiek chce dostrajać.

**Dlaczego osobne sekcje, a nie jeden szablon z placeholderami:** jeden
szablon dałby kontrolę nad kolejnością, ale traci warunkowość. Gdy nadawca nie
ma przypisanego pokoju, `{pokój}` byłoby puste i zostałoby kalekie zdanie
"Nadawca znajduje się w lokalizacji: .". Tylko silnik wie, czy dane w ogóle
istnieją, więc to on musi decydować o pominięciu CAŁEJ sekcji. Ratowanie tego
regułą "pusty placeholder kasuje akapit" byłoby magią, która zaskakuje.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from shared import ConfigStore, get_logger

logger = get_logger("regis.world.prompt_sections")

# Podstawienia — zamknięty, udokumentowany zestaw. Klucze widoczne dla użytkownika
# są po polsku, bo to on je wpisuje w UI.
PLACEHOLDER_TIME = "{czas}"
PLACEHOLDER_ROOM = "{pokój}"
PLACEHOLDER_DEVICES = "{lista_urządzeń}"


@dataclass(frozen=True)
class SectionSpec:
    """Metadane jednej sekcji — do zbudowania UI bez duplikowania tekstów w JS."""

    key: str
    label: str
    default: str
    placeholders: tuple[str, ...]
    condition: str
    """Kiedy sekcja się pojawia — opis dla użytkownika, nie kod. Warunek zna silnik."""


SECTION_SPECS: tuple[SectionSpec, ...] = (
    SectionSpec(
        key="datetime",
        label="Data i godzina",
        default=f"Aktualna data i godzina: {PLACEHOLDER_TIME}.",
        placeholders=(PLACEHOLDER_TIME,),
        condition="Zawsze",
    ),
    SectionSpec(
        key="delivery_voice",
        label="Dostawa: odpowiedź czytana na głos",
        default=(
            "Twoja odpowiedź zostanie odczytana na głos (synteza mowy) — odpowiadaj "
            "krótkimi zdaniami, unikaj Markdown i list, dobierz treść pod słuchanie."
        ),
        placeholders=(),
        condition="Gdy klient ma głośnik",
    ),
    SectionSpec(
        key="delivery_text",
        label="Dostawa: odpowiedź wyświetlana jako tekst",
        default="Twoja odpowiedź zostanie wyświetlona jako tekst — Markdown jest dozwolony.",
        placeholders=(),
        condition="Gdy klient nie ma głośnika",
    ),
    SectionSpec(
        key="location",
        label="Lokalizacja nadawcy",
        default=f"Nadawca znajduje się w lokalizacji: {PLACEHOLDER_ROOM}.",
        placeholders=(PLACEHOLDER_ROOM,),
        condition="Gdy nadawca ma przypisany pokój",
    ),
    SectionSpec(
        key="devices",
        label="Urządzenia",
        default=f"Dostępne urządzenia (adresuj je po podanym entity_id):\n{PLACEHOLDER_DEVICES}",
        placeholders=(PLACEHOLDER_DEVICES,),
        condition="Gdy są zadeklarowane urządzenia lub grupy",
    ),
    SectionSpec(
        key="extra",
        label="Dodatkowe instrukcje",
        default="",
        placeholders=(),
        condition="Zawsze, gdy niepuste",
    ),
)

SECTION_SPECS_BY_KEY = {spec.key: spec for spec in SECTION_SPECS}


class PromptSectionsConfig(BaseModel):
    """Nadpisania sekcji. `None` = użyj domyślnej, `""` = pomiń sekcję całkowicie.

    Rozróżnienie jest celowe i widoczne w UI: wyczyszczenie pola to realna
    decyzja ("nie chcę znacznika czasu w prompcie"), a nie to samo co
    przywrócenie wartości domyślnej.
    """

    datetime: str | None = Field(default=None)
    delivery_voice: str | None = Field(default=None)
    delivery_text: str | None = Field(default=None)
    location: str | None = Field(default=None)
    devices: str | None = Field(default=None)
    extra: str | None = Field(default=None)


class PromptSectionStore:
    """Magazyn nadpisań sekcji — singleton na plik, mirror `HomeAssistantConfig`."""

    def __init__(self, data_dir: Path) -> None:
        self._store: ConfigStore[PromptSectionsConfig] = ConfigStore(
            PromptSectionsConfig, data_dir.resolve() / "prompt_sections.json"
        )

    async def load(self) -> PromptSectionsConfig:
        return await asyncio.to_thread(self._store.load)

    async def save(self, config: PromptSectionsConfig) -> None:
        await asyncio.to_thread(self._store.save, config)
        logger.info("Zapisano sekcje kontekstu tury.")


def resolve_section(
    config: PromptSectionsConfig, key: str, substitutions: dict[str, str] | None = None
) -> str | None:
    """Zwraca gotowy tekst sekcji albo `None`, gdy sekcja ma zostać pominięta.

    Podstawienia przekazywane są słownikiem (a nie `**kwargs`), bo klucze są
    dosłownymi placeholderami widocznymi dla użytkownika — `"{czas}"` nie jest
    poprawną nazwą argumentu Pythona.

    Podstawianie przez jawny `str.replace`, **nigdy `str.format`** — ten drugi
    wysypuje się `KeyError`/`IndexError` na każdym nawiasie klamrowym w tekście
    użytkownika, a ludzie wklejają do promptów przykłady JSON. Nieznane
    `{cokolwiek}` zostaje tu nietknięte, zamiast wywalić całą turę.
    """
    spec = SECTION_SPECS_BY_KEY[key]
    override = getattr(config, key)
    template = spec.default if override is None else override
    if not template:
        return None

    for placeholder, value in (substitutions or {}).items():
        template = template.replace(placeholder, value)
    return template

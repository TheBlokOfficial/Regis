"""Sekcje kontekstu tury — komponowalna lista bloków tekstu z warunkami.

Do tej pory wszystkie zdania o świecie były literałami w `world/engine.py`, więc
zmiana instrukcji typu "odpowiadaj krótko, bo to pójdzie na głos" wymagała edycji
kodu. Pierwsza wersja tego modułu wyniosła je do konfiguracji, ale jako **stały
zestaw sześciu slotów** — czyli dokładnie tego, co silnik akurat liczy. Nie dało
się w nim wyrazić "gdy nadawca jest w Salonie, dodaj instrukcję X".

Dziś sekcje są **listą**: użytkownik dodaje, usuwa i przestawia własne bloki, a
każdemu przypisuje warunek pojawienia się (z opcjonalną negacją).

**Dlaczego to nadal nie jest język szablonów.** Warunki pochodzą z zamkniętej
listy zdefiniowanej tutaj i są ewaluowane w Pythonie — użytkownik ich nie *pisze*,
tylko *wybiera*. Nie da się zrobić literówki w składni, nie ma sandboxa ani
tracebacków z cudzego kodu. Zyskujemy kompozycję, nie interpreter.

**Granica edytowalności zostaje bez zmian**: użytkownik edytuje to, co agent ma
*usłyszeć*; silnik renderuje *dane*. Format wiersza urządzenia i nagłówki pokoi
są dalej w kodzie — zepsuty szablon wiersza po cichu zamieniłby całą listę
urządzeń w śmieci, a to nie jest tekst, który ktokolwiek chce dostrajać.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field
from shared import ConfigStore, get_logger

logger = get_logger("regis.world.prompt_sections")

# --------------------------------------------------------------------------
# Podstawienia — zamknięty zestaw. Klucze są po polsku, bo użytkownik wpisuje
# je ręcznie w UI.
# --------------------------------------------------------------------------

PLACEHOLDER_TIME = "{czas}"
PLACEHOLDER_ROOM = "{pokój}"
PLACEHOLDER_DEVICES = "{lista_urządzeń}"


@dataclass(frozen=True)
class PlaceholderSpec:
    token: str
    label: str
    guaranteed_by: tuple[str, ...]
    """Warunki, przy których wartość na pewno istnieje. Pusta krotka = zawsze."""


# --------------------------------------------------------------------------
# Fakty tury — jedyne wejście warunków. Silnik składa to raz, warunki są
# czystymi funkcjami, więc dają się testować bez żadnego I/O.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnFacts:
    now: str
    capabilities: frozenset[str]
    room_id: str | None
    room_name: str | None
    device_list: str | None
    ha_configured: bool


@dataclass(frozen=True)
class ConditionSpec:
    key: str
    label: str
    predicate: Callable[[TurnFacts, str | None], bool]
    param_source: str | None = None
    """Skąd UI ma wziąć listę wartości parametru (`rooms`) — `None` = bez parametru."""


CONDITION_SPECS: tuple[ConditionSpec, ...] = (
    ConditionSpec("always", "Zawsze", lambda f, p: True),
    ConditionSpec("client_has_speaker", "Klient ma głośnik", lambda f, p: "speaker" in f.capabilities),
    ConditionSpec("client_has_mic", "Klient ma mikrofon", lambda f, p: "mic" in f.capabilities),
    ConditionSpec("client_has_room", "Nadawca ma przypisany pokój", lambda f, p: f.room_id is not None),
    ConditionSpec(
        "client_in_room",
        "Nadawca jest w pokoju",
        lambda f, p: p is not None and f.room_id == p,
        param_source="rooms",
    ),
    ConditionSpec("has_devices", "Są zadeklarowane urządzenia", lambda f, p: bool(f.device_list)),
    ConditionSpec("ha_configured", "Home Assistant skonfigurowany", lambda f, p: f.ha_configured),
)

CONDITION_SPECS_BY_KEY = {spec.key: spec for spec in CONDITION_SPECS}

PLACEHOLDER_SPECS: tuple[PlaceholderSpec, ...] = (
    PlaceholderSpec(PLACEHOLDER_TIME, "Data i godzina", ()),
    PlaceholderSpec(PLACEHOLDER_ROOM, "Nazwa pokoju nadawcy", ("client_has_room", "client_in_room")),
    PlaceholderSpec(PLACEHOLDER_DEVICES, "Lista urządzeń", ("has_devices",)),
)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


class PromptSection(BaseModel):
    """Jeden blok tekstu wraz z warunkiem, przy którym trafia do promptu."""

    id: str = Field(default_factory=lambda: f"sec_{uuid.uuid4().hex[:8]}")
    label: str = Field(default="Sekcja", description="Nazwa widoczna wyłącznie w UI")
    text: str = Field(default="")
    condition: str = Field(default="always")
    condition_param: str | None = Field(default=None)
    negated: bool = Field(default=False, description="Odwraca warunek — 'gdy NIE …'")


class PromptSectionsConfig(BaseModel):
    """Uporządkowana lista sekcji. **Kolejność listy = kolejność w prompcie.**"""

    sections: list[PromptSection] = Field(default_factory=list)


def default_sections() -> list[PromptSection]:
    """Zestaw startowy — dokładnie to, co wcześniej było zahardkodowane.

    `delivery_text` jest tą samą sekcją co `delivery_voice`, tylko z negacją —
    pierwszy realny przykład tego, że negacja usuwa potrzebę bliźniaczych sekcji.
    """
    return [
        PromptSection(
            id="sec_datetime",
            label="Data i godzina",
            text=f"Aktualna data i godzina: {PLACEHOLDER_TIME}.",
            condition="always",
        ),
        PromptSection(
            id="sec_delivery_voice",
            label="Dostawa głosowa",
            text=(
                "Twoja odpowiedź zostanie odczytana na głos (synteza mowy) — odpowiadaj "
                "krótkimi zdaniami, unikaj Markdown i list, dobierz treść pod słuchanie."
            ),
            condition="client_has_speaker",
        ),
        PromptSection(
            id="sec_delivery_text",
            label="Dostawa tekstowa",
            text="Twoja odpowiedź zostanie wyświetlona jako tekst — Markdown jest dozwolony.",
            condition="client_has_speaker",
            negated=True,
        ),
        PromptSection(
            id="sec_location",
            label="Lokalizacja nadawcy",
            text=f"Nadawca znajduje się w lokalizacji: {PLACEHOLDER_ROOM}.",
            condition="client_has_room",
        ),
        PromptSection(
            id="sec_devices",
            label="Urządzenia",
            text=f"Dostępne urządzenia (adresuj je po podanym entity_id):\n{PLACEHOLDER_DEVICES}",
            condition="has_devices",
        ),
    ]


# Mapowanie starych, płaskich kluczy na ID sekcji zestawu startowego — używane
# wyłącznie przy migracji (patrz `PromptSectionStore.load`).
_LEGACY_KEY_TO_SECTION_ID = {
    "datetime": "sec_datetime",
    "delivery_voice": "sec_delivery_voice",
    "delivery_text": "sec_delivery_text",
    "location": "sec_location",
    "devices": "sec_devices",
}


class PromptSectionStore:
    """Magazyn sekcji — jeden plik JSON, mirror wzorca singletona `HomeAssistantConfig`."""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir.resolve() / "prompt_sections.json"
        self._store: ConfigStore[PromptSectionsConfig] = ConfigStore(PromptSectionsConfig, self._path)

    async def load(self) -> PromptSectionsConfig:
        """Wczytuje sekcje, migrując po drodze stary, płaski format.

        Pierwsza wersja tego modułu trzymała sześć nazwanych pól (`{"datetime": …}`)
        zamiast listy. Migracja przenosi ewentualne nadpisania do odpowiadających im
        sekcji zestawu startowego — użytkownik mógł zdążyć coś wpisać, a ciche
        zgubienie jego tekstu byłoby przykrą niespodzianką.
        """
        raw = await asyncio.to_thread(self._read_raw)
        if raw is None:
            seeded = PromptSectionsConfig(sections=default_sections())
            await self.save(seeded)
            return seeded
        if "sections" in raw:
            return PromptSectionsConfig.model_validate(raw)

        migrated = _migrate_legacy(raw)
        logger.info("Zmigrowano sekcje kontekstu tury ze starego, płaskiego formatu do listy.")
        await self.save(migrated)
        return migrated

    async def save(self, config: PromptSectionsConfig) -> None:
        await asyncio.to_thread(self._store.save, config)

    async def reset(self) -> PromptSectionsConfig:
        seeded = PromptSectionsConfig(sections=default_sections())
        await self.save(seeded)
        logger.info("Przywrócono domyślny zestaw sekcji kontekstu tury.")
        return seeded

    def _read_raw(self) -> dict[str, Any] | None:
        """Surowy odczyt JSON — potrzebny, bo `ConfigStore.load()` zwaliduje plik do
        nowego modelu i stary kształt cicho zniknąłby jako pusta lista."""
        import json

        if not self._path.exists():
            return None
        try:
            with self._path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError) as err:
            logger.warning(f"Nie udało się odczytać sekcji kontekstu tury [{self._path}]: {err}")
            return None


def _migrate_legacy(raw: dict[str, Any]) -> PromptSectionsConfig:
    sections = default_sections()
    by_id = {section.id: section for section in sections}
    for legacy_key, section_id in _LEGACY_KEY_TO_SECTION_ID.items():
        override = raw.get(legacy_key)
        if isinstance(override, str) and section_id in by_id:
            by_id[section_id].text = override
    extra = raw.get("extra")
    if isinstance(extra, str) and extra:
        sections.append(PromptSection(id="sec_extra", label="Dodatkowe instrukcje", text=extra, condition="always"))
    return PromptSectionsConfig(sections=sections)


# --------------------------------------------------------------------------
# Ewaluacja
# --------------------------------------------------------------------------


def section_applies(section: PromptSection, facts: TurnFacts) -> bool:
    """Czy sekcja trafia do promptu tej tury. Nieznany warunek = sekcja pomijana
    (bezpieczniej niż wpuścić do promptu blok, którego reguły nie rozumiemy)."""
    spec = CONDITION_SPECS_BY_KEY.get(section.condition)
    if spec is None:
        logger.warning(f"Nieznany warunek sekcji [{section.id}]: '{section.condition}' — sekcja pominięta.")
        return False
    result = spec.predicate(facts, section.condition_param)
    return not result if section.negated else result


def render_section(section: PromptSection, facts: TurnFacts) -> str | None:
    """Zwraca gotowy tekst sekcji albo `None`, gdy warunek niespełniony lub tekst pusty.

    Podstawianie przez jawny `str.replace`, **nigdy `str.format`** — ten drugi
    wysypuje się `KeyError`/`IndexError` na każdym nawiasie klamrowym w tekście
    użytkownika, a ludzie wklejają do promptów przykłady JSON. Nieznane
    `{cokolwiek}` zostaje nietknięte, zamiast wywalić całą turę.
    """
    if not section.text or not section_applies(section, facts):
        return None

    rendered = section.text
    for token, value in (
        (PLACEHOLDER_TIME, facts.now),
        (PLACEHOLDER_ROOM, facts.room_name or ""),
        (PLACEHOLDER_DEVICES, facts.device_list or ""),
    ):
        rendered = rendered.replace(token, value)
    return rendered


def section_warnings(section: PromptSection) -> list[str]:
    """Ostrzeżenia dla UI — **nie blokują zapisu**, bo użycie niegwarantowanego
    podstawienia bywa zamierzone. Chodzi o to, żeby użytkownik nie odkrył dopiero
    w rozmowie z agentem, że jego sekcja renderuje 'Nadawca jest w: .'."""
    warnings: list[str] = []
    for spec in PLACEHOLDER_SPECS:
        if spec.token not in section.text or not spec.guaranteed_by:
            continue
        if section.negated or section.condition not in spec.guaranteed_by:
            labels = " lub ".join(CONDITION_SPECS_BY_KEY[key].label for key in spec.guaranteed_by)
            warnings.append(
                f"Sekcja używa {spec.token}, ale jej warunek nie gwarantuje, że wartość istnieje "
                f"(gwarantuje ją: {labels}). Przy braku wartości podstawi się pusty tekst."
            )
    if section.condition not in CONDITION_SPECS_BY_KEY:
        warnings.append(f"Nieznany warunek '{section.condition}' — sekcja nigdy się nie pojawi.")
    elif CONDITION_SPECS_BY_KEY[section.condition].param_source and not section.condition_param:
        warnings.append("Warunek wymaga wybrania wartości — bez niej sekcja nigdy się nie pojawi.")
    return warnings

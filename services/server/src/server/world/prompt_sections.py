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
PLACEHOLDER_DATE = "{data}"
PLACEHOLDER_CLOCK = "{godzina}"
PLACEHOLDER_WEEKDAY = "{dzień_tygodnia}"
PLACEHOLDER_ROOM = "{pokój}"
PLACEHOLDER_ROOMS = "{lista_pokoi}"
PLACEHOLDER_DEVICES = "{lista_urządzeń}"
PLACEHOLDER_ROOM_DEVICES = "{urządzenia_w_pokoju}"
PLACEHOLDER_GROUPS = "{lista_grup}"
PLACEHOLDER_CLIENT = "{nazwa_klienta}"
PLACEHOLDER_CAPABILITIES = "{możliwości_klienta}"


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
    """Wszystko, co silnik wie o TEJ turze. Jedyne wejście warunków i podstawień.

    Składane raz na turę w `WorldEngine.build()`, dzięki czemu każdy warunek jest czystą
    funkcją i testuje się bez żadnego I/O."""

    now: str
    date: str
    clock: str
    weekday: str
    capabilities: frozenset[str]
    room_id: str | None
    room_name: str | None
    client_name: str | None
    device_list: str | None
    room_device_list: str | None
    room_names: tuple[str, ...] = ()
    group_names: tuple[str, ...] = ()
    ha_configured: bool = False


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
    ConditionSpec(
        "has_devices_in_room",
        "Są urządzenia w pokoju nadawcy",
        lambda f, p: bool(f.room_device_list),
    ),
    ConditionSpec("has_groups", "Są zdefiniowane grupy", lambda f, p: bool(f.group_names)),
    ConditionSpec("client_has_name", "Klient ma nadaną nazwę", lambda f, p: bool(f.client_name)),
    ConditionSpec("ha_configured", "Home Assistant skonfigurowany", lambda f, p: f.ha_configured),
)

CONDITION_SPECS_BY_KEY = {spec.key: spec for spec in CONDITION_SPECS}

PLACEHOLDER_SPECS: tuple[PlaceholderSpec, ...] = (
    PlaceholderSpec(PLACEHOLDER_TIME, "Data i godzina", ()),
    PlaceholderSpec(PLACEHOLDER_DATE, "Sama data", ()),
    PlaceholderSpec(PLACEHOLDER_CLOCK, "Sama godzina", ()),
    PlaceholderSpec(PLACEHOLDER_WEEKDAY, "Dzień tygodnia", ()),
    PlaceholderSpec(PLACEHOLDER_ROOMS, "Lista wszystkich pokoi", ()),
    PlaceholderSpec(PLACEHOLDER_CAPABILITIES, "Możliwości klienta", ()),
    PlaceholderSpec(PLACEHOLDER_ROOM, "Nazwa pokoju nadawcy", ("client_has_room", "client_in_room")),
    PlaceholderSpec(PLACEHOLDER_CLIENT, "Nazwa klienta", ("client_has_name",)),
    PlaceholderSpec(PLACEHOLDER_DEVICES, "Lista wszystkich urządzeń", ("has_devices",)),
    PlaceholderSpec(PLACEHOLDER_ROOM_DEVICES, "Urządzenia w pokoju nadawcy", ("has_devices_in_room",)),
    PlaceholderSpec(PLACEHOLDER_GROUPS, "Lista grup", ("has_groups",)),
)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


class PromptSection(BaseModel):
    """Jeden blok tekstu wraz z warunkiem — z DWIEMA gałęziami: co powiedzieć, gdy warunek
    jest spełniony, i co gdy nie jest.

    Wcześniej gałąź "gdy nie" wymagała **osobnej sekcji** z flagą `negated`, przez co ta
    sama decyzja ("czy klient ma głośnik?") była rozrzucona po dwóch wpisach listy, które
    nic formalnie nie łączyło — dało się je niezależnie przestawić, przez co warunek i jego
    zaprzeczenie mogły wylądować w odległych miejscach promptu. Dwa pola w jednym wpisie
    kosztują utratę niezależnej pozycji obu gałęzi (świadomy wybór) i usuwają checkbox,
    który był jednym z ostatnich natywnych kontrolek przeglądarki w tym projekcie.

    Obie gałęzie są opcjonalne: pusta = przy tym wyniku warunku sekcja po prostu nie
    dokłada niczego do promptu.
    """

    id: str = Field(default_factory=lambda: f"sec_{uuid.uuid4().hex[:8]}")
    label: str = Field(default="Sekcja", description="Nazwa widoczna wyłącznie w UI")
    text: str = Field(default="", description="Tekst używany, gdy warunek JEST spełniony")
    text_negated: str = Field(default="", description="Tekst używany, gdy warunek NIE jest spełniony")
    condition: str = Field(default="always")
    condition_param: str | None = Field(default=None)


class PromptSectionsConfig(BaseModel):
    """Uporządkowana lista sekcji. **Kolejność listy = kolejność w prompcie.**"""

    sections: list[PromptSection] = Field(default_factory=list)


def default_sections() -> list[PromptSection]:
    """Zestaw startowy — dokładnie to, co wcześniej było zahardkodowane.

    Dostawa głosowa i tekstowa to DWIE GAŁĘZIE JEDNEJ sekcji — to jest dokładnie ten
    przypadek, dla którego dwa pola tekstowe zastąpiły parę sekcji z flagą negacji.
    """
    return [
        PromptSection(
            id="sec_datetime",
            label="Data i godzina",
            text=f"Aktualna data i godzina: {PLACEHOLDER_TIME}.",
            condition="always",
        ),
        PromptSection(
            id="sec_delivery",
            label="Sposób dostawy",
            text=(
                "Twoja odpowiedź zostanie odczytana na głos (synteza mowy) — odpowiadaj "
                "krótkimi zdaniami, unikaj Markdown i list, dobierz treść pod słuchanie."
            ),
            text_negated="Twoja odpowiedź zostanie wyświetlona jako tekst — Markdown jest dozwolony.",
            condition="client_has_speaker",
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
    "delivery_voice": "sec_delivery",
    "location": "sec_location",
    "devices": "sec_devices",
}

# `delivery_text` był w płaskim formacie osobnym kluczem, a dziś jest drugą GAŁĘZIĄ
# sekcji `sec_delivery` — stąd osobne mapowanie, nie wpis wyżej.
_LEGACY_NEGATED_KEY_TO_SECTION_ID = {"delivery_text": "sec_delivery"}


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
            merged = _merge_negated_pairs(raw["sections"] or [])
            if merged is not None:
                logger.info("Scalono pary sekcji warunek/negacja w pojedyncze sekcje z dwiema gałęziami.")
                await self.save(merged)
                return merged
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


def _merge_negated_pairs(raw_sections: list[dict[str, Any]]) -> PromptSectionsConfig | None:
    """Migracja z modelu "osobna sekcja z flagą `negated`" na dwie gałęzie w jednej sekcji.

    Zwraca `None`, gdy nie ma czego migrować (plik już w nowym formacie) — wtedy nie
    zapisujemy pliku bez potrzeby.

    Sekcje zanegowane są **scalane z partnerem**: pierwszą niezanegowaną sekcją o tym samym
    warunku i parametrze. Dopasowanie jest zawężone do dokładnie tej pary, bo tylko ona
    opisuje jedną decyzję rozbitą na dwa wpisy; zanegowana sekcja bez partnera zostaje
    osobnym wpisem z wypełnioną wyłącznie gałęzią "gdy NIE spełniony" (zachowanie identyczne
    jak przed migracją). Etykieta i pozycja pochodzą od partnera niezanegowanego — to on
    opisuje warunek wprost, więc jest czytelniejszym nagłówkiem scalonej sekcji.
    """
    if not any(entry.get("negated") for entry in raw_sections):
        return None

    merged: list[PromptSection] = []
    index_by_condition: dict[tuple[str, str | None], int] = {}

    for entry in raw_sections:
        key = (entry.get("condition", "always"), entry.get("condition_param"))
        text = entry.get("text", "") or ""
        if not entry.get("negated"):
            index_by_condition[key] = len(merged)
            merged.append(
                PromptSection(
                    id=entry.get("id") or f"sec_{uuid.uuid4().hex[:8]}",
                    label=entry.get("label", "Sekcja"),
                    text=text,
                    condition=key[0],
                    condition_param=key[1],
                )
            )
            continue

        partner_index = index_by_condition.get(key)
        if partner_index is not None and not merged[partner_index].text_negated:
            merged[partner_index].text_negated = text
            continue
        merged.append(
            PromptSection(
                id=entry.get("id") or f"sec_{uuid.uuid4().hex[:8]}",
                label=entry.get("label", "Sekcja"),
                text="",
                text_negated=text,
                condition=key[0],
                condition_param=key[1],
            )
        )

    return PromptSectionsConfig(sections=merged)


def _migrate_legacy(raw: dict[str, Any]) -> PromptSectionsConfig:
    sections = default_sections()
    by_id = {section.id: section for section in sections}
    for legacy_key, section_id in _LEGACY_KEY_TO_SECTION_ID.items():
        override = raw.get(legacy_key)
        if isinstance(override, str) and section_id in by_id:
            by_id[section_id].text = override
    for legacy_key, section_id in _LEGACY_NEGATED_KEY_TO_SECTION_ID.items():
        override = raw.get(legacy_key)
        if isinstance(override, str) and section_id in by_id:
            by_id[section_id].text_negated = override
    extra = raw.get("extra")
    if isinstance(extra, str) and extra:
        sections.append(PromptSection(id="sec_extra", label="Dodatkowe instrukcje", text=extra, condition="always"))
    return PromptSectionsConfig(sections=sections)


# --------------------------------------------------------------------------
# Ewaluacja
# --------------------------------------------------------------------------


def section_condition_holds(section: PromptSection, facts: TurnFacts) -> bool | None:
    """Czy warunek sekcji jest spełniony. `None` = warunku nie da się ocenić (nieznany
    klucz) i sekcja jest wtedy pomijana w całości — bezpieczniej niż wpuścić do promptu
    blok, którego reguł nie rozumiemy."""
    spec = CONDITION_SPECS_BY_KEY.get(section.condition)
    if spec is None:
        logger.warning(f"Nieznany warunek sekcji [{section.id}]: '{section.condition}' — sekcja pominięta.")
        return None
    return spec.predicate(facts, section.condition_param)


def render_section(section: PromptSection, facts: TurnFacts) -> str | None:
    """Zwraca tekst gałęzi pasującej do wyniku warunku albo `None`, gdy ta gałąź jest pusta.

    Pusta gałąź to poprawny, częsty stan — "gdy warunek niespełniony nie mów nic" — a nie
    błąd konfiguracji.

    Podstawianie przez jawny `str.replace`, **nigdy `str.format`** — ten drugi
    wysypuje się `KeyError`/`IndexError` na każdym nawiasie klamrowym w tekście
    użytkownika, a ludzie wklejają do promptów przykłady JSON. Nieznane
    `{cokolwiek}` zostaje nietknięte, zamiast wywalić całą turę.
    """
    holds = section_condition_holds(section, facts)
    if holds is None:
        return None

    template = section.text if holds else section.text_negated
    if not template:
        return None

    rendered = template
    for token, value in (
        (PLACEHOLDER_TIME, facts.now),
        (PLACEHOLDER_DATE, facts.date),
        (PLACEHOLDER_CLOCK, facts.clock),
        (PLACEHOLDER_WEEKDAY, facts.weekday),
        (PLACEHOLDER_ROOM, facts.room_name or ""),
        (PLACEHOLDER_ROOMS, ", ".join(facts.room_names)),
        (PLACEHOLDER_CLIENT, facts.client_name or ""),
        (PLACEHOLDER_CAPABILITIES, ", ".join(sorted(facts.capabilities))),
        (PLACEHOLDER_DEVICES, facts.device_list or ""),
        (PLACEHOLDER_ROOM_DEVICES, facts.room_device_list or ""),
        (PLACEHOLDER_GROUPS, ", ".join(facts.group_names)),
    ):
        rendered = rendered.replace(token, value)
    return rendered


def section_warnings(section: PromptSection) -> list[str]:
    """Ostrzeżenia dla UI — **nie blokują zapisu**, bo użycie niegwarantowanego
    podstawienia bywa zamierzone. Chodzi o to, żeby użytkownik nie odkrył dopiero
    w rozmowie z agentem, że jego sekcja renderuje 'Nadawca jest w: .'."""
    warnings: list[str] = []
    for spec in PLACEHOLDER_SPECS:
        if not spec.guaranteed_by:
            continue
        # Gałąź "gdy spełniony" korzysta z gwarancji warunku; gałąź "gdy NIE spełniony"
        # z definicji działa wtedy, gdy warunek nie zachodzi — więc żadna gwarancja jej
        # nie obejmuje i użycie tam podstawienia zawsze zasługuje na ostrzeżenie.
        in_positive = spec.token in section.text
        in_negative = spec.token in section.text_negated
        if not in_positive and not in_negative:
            continue
        guaranteed_positive = section.condition in spec.guaranteed_by
        if in_negative or not guaranteed_positive:
            labels = " lub ".join(CONDITION_SPECS_BY_KEY[key].label for key in spec.guaranteed_by)
            where = "gałąź 'gdy NIE spełniony'" if in_negative and guaranteed_positive else "Sekcja"
            warnings.append(
                f"{where} używa {spec.token}, ale warunek nie gwarantuje, że wartość istnieje "
                f"(gwarantuje ją: {labels}). Przy braku wartości podstawi się pusty tekst."
            )
    if section.condition not in CONDITION_SPECS_BY_KEY:
        warnings.append(f"Nieznany warunek '{section.condition}' — sekcja nigdy się nie pojawi.")
    elif CONDITION_SPECS_BY_KEY[section.condition].param_source and not section.condition_param:
        warnings.append("Warunek wymaga wybrania wartości — bez niej sekcja nigdy się nie pojawi.")
    return warnings

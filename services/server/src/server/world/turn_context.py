"""Zamiana stanu Świata na TEKST tury — fakty, lista urządzeń, złożony kontekst.

Wydzielone z `WorldEngine.build()`, gdzie renderowanie mieszało się z odczytem
konfiguracji i budową narzędzi. Tutaj nie ma żadnego I/O: funkcje dostają gotowe
dane i zwracają stringi, więc każdą z nich da się sprawdzić bez dysku, sieci
i bez podnoszenia silnika.

Granica edytowalności (patrz `prompt_sections.py`): użytkownik edytuje to, co agent
ma *usłyszeć*; ten moduł renderuje *dane*. Format wiersza urządzenia i nagłówki
pokoi zostają w kodzie — zepsuty szablon wiersza po cichu zamieniłby całą listę
urządzeń w śmieci.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from server.world.models import Device, DeviceGroup, RoomInstanceConfig, SenderProfile
from server.world.prompt_sections import PromptSectionsConfig, TurnFacts, render_section
from server.world.tools.home_assistant import TOOL_NAMES

# Nazwy dni po polsku — `datetime.strftime("%A")` zależy od locale procesu, więc dawałoby
# raz "Monday", raz "poniedziałek", zależnie od maszyny.
_WEEKDAY_NAMES = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")


def format_capabilities(device: Device) -> str:
    """`turn_on[brightness, color_temp], get_state` — możliwości urządzenia w jednym wierszu."""
    labels = []
    for tool_name, features in sorted(device.capabilities.items()):
        labels.append(f"{tool_name}[{', '.join(sorted(features))}]" if features else tool_name)
    return ", ".join(labels) if labels else "brak"


def _device_line(device: Device) -> str:
    return f"- [{device.id}] {device.name} (możliwości: {format_capabilities(device)})"


def render_devices_section(
    devices: list[Device],
    groups: list[DeviceGroup],
    rooms_by_id: dict[str, RoomInstanceConfig],
    current_room_id: str | None,
) -> str:
    """Lista urządzeń posegregowana wg `Device.room_id` (pełnoprawny pokój World,
    niezależny od Home Assistant) — pełna adresowalność zawsze zachowana, segregacja
    to wyłącznie prezentacja. Urządzenie wskazujące na usunięty/nieznany `room_id`
    traktowane jest jak nieprzypisane (bez cascade delete przy usuwaniu pokoju).

    **Bez zdania wprowadzającego** — to należy do edytowalnej sekcji `devices`
    (`prompt_sections.py`), która wstawia tę listę w miejsce `{lista_urządzeń}`.
    Trzymanie nagłówka w obu miejscach dawało go w prompcie dwukrotnie.
    """
    by_room: dict[str, list[Device]] = {}
    unassigned: list[Device] = []
    for device in devices:
        if device.room_id and device.room_id in rooms_by_id:
            by_room.setdefault(device.room_id, []).append(device)
        else:
            unassigned.append(device)

    lines: list[str] = []
    for room_id, room_devices in sorted(by_room.items(), key=lambda item: item[0] != current_room_id):
        is_current = room_id == current_room_id
        lines.append(f"### {rooms_by_id[room_id].name}" + (" (Twoja lokalizacja)" if is_current else ""))
        lines.extend(_device_line(device) for device in room_devices)
    if unassigned:
        lines.append("### (bez przypisanego pokoju)")
        lines.extend(_device_line(device) for device in unassigned)
    if groups:
        lines.append("### Grupy")
        group_capabilities = ", ".join(TOOL_NAMES)
        for group in groups:
            lines.append(f"- [{group.id}] {group.name} (możliwości: {group_capabilities})")
    return "\n".join(lines)


def render_room_devices(devices: list[Device]) -> str | None:
    """Sam pokój nadawcy, bez nagłówków i bez grup — pozwala napisać sekcję w rodzaju
    „masz pod ręką: {urządzenia_w_pokoju}", nie zalewając promptu całym domem."""
    if not devices:
        return None
    return "\n".join(_device_line(device) for device in devices)


def build_turn_facts(
    *,
    now: datetime,
    profile: SenderProfile | None,
    current_room: RoomInstanceConfig | None,
    rooms_by_id: dict[str, RoomInstanceConfig],
    devices: list[Device],
    groups: list[DeviceGroup],
    ha_configured: bool,
) -> TurnFacts:
    """Składa komplet faktów tej tury — jedyne wejście warunków i podstawień sekcji.

    Modalność wyprowadzana jest z trwałych `capabilities` klienta, nie z flagi
    wywołania (dawne `voice_mode`): „ten klient ma głośnik" to fakt o rzeczy
    w świecie, dokładnie jak `Device.capabilities`.
    """
    device_list = (
        render_devices_section(
            devices,
            groups,
            rooms_by_id=rooms_by_id,
            current_room_id=current_room.id if current_room else None,
        )
        if (devices or groups)
        else None
    )
    room_devices = [d for d in devices if current_room is not None and d.room_id == current_room.id]

    return TurnFacts(
        now=now.strftime("%Y-%m-%d %H:%M:%S"),
        date=now.strftime("%Y-%m-%d"),
        clock=now.strftime("%H:%M"),
        weekday=_WEEKDAY_NAMES[now.weekday()],
        capabilities=frozenset(c.value for c in profile.capabilities) if profile else frozenset(),
        room_id=current_room.id if current_room else None,
        room_name=current_room.name if current_room else None,
        client_name=profile.display_name if profile else None,
        device_list=device_list,
        room_device_list=render_room_devices(room_devices),
        room_names=tuple(room.name for room in rooms_by_id.values()),
        group_names=tuple(group.name for group in groups),
        ha_configured=ha_configured,
    )


def render_turn_context(sections: PromptSectionsConfig, facts: TurnFacts) -> str | None:
    """Składa kontekst tury z sekcji użytkownika. `None`, gdy żadna nie ma nic do dodania.

    Silnik dostarcza WYŁĄCZNIE dane; o tym, które bloki tekstu się pojawią i w jakiej
    kolejności, decyduje konfiguracja użytkownika."""
    parts = [rendered for section in sections.sections if (rendered := render_section(section, facts)) is not None]
    return "\n\n".join(parts) if parts else None


def sections_gained_after_redirect(
    sections: PromptSectionsConfig,
    original: TurnFacts,
    target_profile: SenderProfile | None,
    target_room_name: str | None,
) -> list[str]:
    """Sekcje, które zaczynają obowiązywać dopiero po przekierowaniu na inny cel.

    Zwracamy RÓŻNICĘ, nie cały kontekst: model dostał już fakty tej tury na starcie,
    więc powtarzanie ich (zwłaszcza listy urządzeń) tylko zaśmiecałoby pętlę ReAct.
    Interesuje nas wyłącznie to, co się zmieniło — typowo ramowanie dostawy, bo cel
    ma głośnik, a pierwotny nadawca mógł go nie mieć.
    """
    # Zmienia się WYŁĄCZNIE to, co zależy od celu (możliwości, pokój, nazwa); reszta
    # faktów tej tury zostaje — stąd `replace` na istniejącym obiekcie zamiast budowania
    # go od zera, przy którym każde nowe pole `TurnFacts` trzeba by pamiętać tu przepisać.
    target_facts = replace(
        original,
        capabilities=frozenset(c.value for c in target_profile.capabilities) if target_profile else frozenset(),
        room_id=target_profile.room_id if target_profile else None,
        room_name=target_room_name,
        client_name=target_profile.display_name if target_profile else None,
    )
    gained: list[str] = []
    for section in sections.sections:
        # Porównujemy WYRENDEROWANY tekst, nie sam fakt "czy warunek zachodzi": po
        # rozdzieleniu na dwie gałęzie sekcja obowiązuje praktycznie zawsze, a realną
        # zmianą jest to, że mówi teraz co innego niż mówiła przed przekierowaniem.
        rendered = render_section(section, target_facts)
        if rendered and rendered != render_section(section, original):
            gained.append(rendered)
    return gained

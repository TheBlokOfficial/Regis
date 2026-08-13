"""Model urządzeń i grup addonu Smart Home.

Agent operuje wyłącznie na tych typach — konkretna integracja stojąca za
urządzeniem nigdy nie jest ujawniana LLM.
"""

from dataclasses import dataclass, field


@dataclass
class Device:
    """Pojedyncze urządzenie dostarczone przez integrację (`DeviceIntegration`).

    :param id: Opaque identyfikator z przestrzenią nazw integracji (np. 'int_ha_main:light.bathroom').
    :param integration_id: ID instancji integracji, która dostarczyła to urządzenie.
    :param name: Przyjazna nazwa widoczna dla agenta/użytkownika.
    :param kind: Kategoria urządzenia (np. 'light', 'switch', 'climate', 'sensor').
    :param capabilities: Zbiór wspieranych capability (np. 'turn_on', 'turn_off', 'get_state').
    :param area: Opcjonalny, luźny tag lokalizacji (bez żadnego rejestru/FK — czysto informacyjny).
    """

    id: str
    integration_id: str
    name: str
    kind: str
    capabilities: set[str] = field(default_factory=set)
    area: str | None = None


@dataclass
class DeviceGroup:
    """Nazwana, dowolna kolekcja urządzeń — niezależna od ich lokalizacji.

    Urządzenia w grupie mogą pochodzić z różnych integracji. Grupa nie ma
    własnej lokalizacji — dziedziczy ją (jeśli w ogóle) po swoich członkach.
    """

    id: str
    name: str
    device_ids: list[str]


class DeviceRegistry:
    """Agreguje urządzenia i grupy ze wszystkich włączonych integracji na czas jednej interakcji agenta.

    Jedyne miejsce w systemie z logiką dopasowania nazwy — integracje nie
    implementują własnego wyszukiwania/rozstrzygania niejednoznaczności.
    """

    def __init__(self, devices: list[Device], groups: list[DeviceGroup] | None = None) -> None:
        self._devices = devices
        self._groups = groups or []
        self._devices_by_id = {d.id: d for d in self._devices}

    def all(self) -> list[Device]:
        """Zwraca wszystkie zarejestrowane urządzenia."""
        return list(self._devices)

    def all_groups(self) -> list[DeviceGroup]:
        """Zwraca wszystkie zarejestrowane grupy."""
        return list(self._groups)

    def get_device(self, device_id: str) -> Device | None:
        """Zwraca urządzenie po jego (namespaced) ID lub None."""
        return self._devices_by_id.get(device_id)

    def group_names_for_device(self, device_id: str) -> list[str]:
        """Zwraca nazwy grup, do których należy dane urządzenie (do adnotacji w list_devices)."""
        return [g.name for g in self._groups if device_id in g.device_ids]

    def by_area(self, area: str | None) -> list[Device]:
        """Zwraca urządzenia z podanego obszaru lub wszystkie, jeśli obszar nie podano."""
        if not area:
            return self.all()
        area_lower = area.strip().lower()
        return [d for d in self._devices if d.area and d.area.lower() == area_lower]

    def resolve(self, name: str) -> Device | DeviceGroup | list[Device | DeviceGroup] | None:
        """Znajduje urządzenie lub grupę po przyjaznej nazwie (jedna wspólna przestrzeń nazw).

        :return: Pojedynczy `Device`/`DeviceGroup` przy jednoznacznym trafieniu,
            lista kandydatów przy niejednoznaczności (może mieszać oba typy),
            lub `None` gdy nic nie pasuje.
        """
        name_lower = name.strip().lower()
        if not name_lower:
            return None

        exact: list[Device | DeviceGroup] = [d for d in self._devices if d.name.lower() == name_lower]
        exact += [g for g in self._groups if g.name.lower() == name_lower]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            return exact

        partial: list[Device | DeviceGroup] = [d for d in self._devices if name_lower in d.name.lower()]
        partial += [g for g in self._groups if name_lower in g.name.lower()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            return partial

        return None

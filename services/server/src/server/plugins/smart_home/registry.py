"""Magazyn urządzeń i grup na czas jednej interakcji agenta — czysto wewnętrzna
sprawa pluginu (Gateway nigdy go nie widzi).

W przeciwieństwie do dzisiejszego `DeviceRegistry` addonu, ten rejestr NIE
dopasowuje po nazwie — agent adresuje encje po opaque ID nadanym przez
Gateway, które plugin tłumaczy z powrotem na wewnętrzny ref (klucz tego
rejestru) zanim w ogóle tu trafi (wizja, sekcja 4.2).
"""

from server.plugins.smart_home.models import Device, DeviceGroup


class DeviceRegistry:
    """Agreguje urządzenia i grupy ze wszystkich włączonych integracji na czas jednej interakcji agenta."""

    def __init__(self, devices: list[Device], groups: list[DeviceGroup] | None = None) -> None:
        self._devices = devices
        self._groups = groups or []
        self._devices_by_id = {d.id: d for d in self._devices}
        self._groups_by_id = {g.id: g for g in self._groups}

    def all(self) -> list[Device]:
        """Zwraca wszystkie zarejestrowane urządzenia."""
        return list(self._devices)

    def all_groups(self) -> list[DeviceGroup]:
        """Zwraca wszystkie zarejestrowane grupy."""
        return list(self._groups)

    def get_device(self, device_id: str) -> Device | None:
        """Zwraca urządzenie po jego (namespaced) wewnętrznym ref lub None."""
        return self._devices_by_id.get(device_id)

    def get_group(self, group_id: str) -> DeviceGroup | None:
        """Zwraca grupę po jej wewnętrznym ref lub None."""
        return self._groups_by_id.get(group_id)

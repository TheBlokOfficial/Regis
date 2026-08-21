"""Klient REST API Home Assistant.

Cała wiedza o formacie danych Home Assistant (entity_id, domain.service,
atrybuty encji) jest zamknięta w tej klasie — narzędzia LLM (`tools.py`)
operują wyłącznie na generycznym modelu `Device`+capability.
"""

from typing import Any, Callable

import httpx
from shared import get_logger

from server.agent.llm import ToolResult
from server.world.models import Device

logger = get_logger("regis.world")

# Domeny encji HA obsługujące włączanie/wyłączanie — wszystkie pozostałe domeny
# udostępniają wyłącznie odczyt stanu ('get_state'). Fallback dla domen bez
# własnego dekodera w `_DOMAIN_DECODERS`.
_TOGGLEABLE_DOMAINS = {"light", "switch", "fan", "input_boolean"}

# `supported_color_modes` implikujące, że encja 'light' wspiera jasność/kolor —
# nowoczesny HA wycofał odpowiadające bity z bitmaski `supported_features`,
# więc jasność/kolor czytamy wyłącznie stąd, nigdy z bitmaski.
_COLOR_MODES_IMPLYING_BRIGHTNESS = {
    "brightness", "color_temp", "hs", "rgb", "rgbw", "rgbww", "xy", "white",
}
_COLOR_MODES_IMPLYING_COLOR = {"hs", "rgb", "rgbw", "rgbww", "xy", "color_temp"}
_LIGHT_FEATURE_EFFECT = 4


def _decode_light(attributes: dict[str, Any]) -> dict[str, frozenset[str]]:
    """Dekoduje capabilities encji domeny 'light' z jej atrybutów HA.

    Jasność/kolor/efekt nie są osobnymi narzędziami — `light/turn_on` w HA
    przyjmuje je jako opcjonalne parametry tego samego wywołania, więc ich
    cechy trafiają jako granularne cechy pod klucz `"turn_on"` (patrz
    `tools.py`, gdzie `turn_on` niesie te opcjonalne pola w jednym schemacie).
    """
    turn_on_features: set[str] = set()
    color_modes = set(attributes.get("supported_color_modes") or [])
    features_bitmask = attributes.get("supported_features") or 0

    if color_modes & _COLOR_MODES_IMPLYING_BRIGHTNESS:
        turn_on_features.add("brightness")

    turn_on_features |= color_modes & _COLOR_MODES_IMPLYING_COLOR

    if features_bitmask & _LIGHT_FEATURE_EFFECT and attributes.get("effect_list"):
        turn_on_features.add("effect")

    return {
        "turn_on": frozenset(turn_on_features),
        "turn_off": frozenset(),
        "get_state": frozenset(),
    }


_DOMAIN_DECODERS: dict[str, Callable[[dict[str, Any]], dict[str, frozenset[str]]]] = {
    "light": _decode_light,
}


def _capabilities_for_entity(domain: str, attributes: dict[str, Any]) -> dict[str, frozenset[str]]:
    decoder = _DOMAIN_DECODERS.get(domain)
    if decoder:
        return decoder(attributes)
    if domain in _TOGGLEABLE_DOMAINS:
        return {"turn_on": frozenset(), "turn_off": frozenset(), "get_state": frozenset()}
    return {"get_state": frozenset()}


def _format_state_text(entity_id: str, domain: str, state: str, attributes: dict[str, Any]) -> str:
    """Formatuje surowy stan encji HA na czytelny tekst — jedyne miejsce, gdzie interpretujemy atrybuty HA."""
    friendly = attributes.get("friendly_name", entity_id)

    if domain == "sensor":
        unit = attributes.get("unit_of_measurement", "")
        return f"{friendly}: {state}{f' {unit}' if unit else ''}"

    if domain == "climate":
        parts = [f"tryb: {state}"]
        current = attributes.get("current_temperature")
        target = attributes.get("temperature")
        if current is not None:
            parts.append(f"aktualna temperatura: {current}°C")
        if target is not None:
            parts.append(f"temperatura docelowa: {target}°C")
        return f"{friendly}: " + ", ".join(parts)

    if domain in _TOGGLEABLE_DOMAINS:
        status = {"on": "włączone", "off": "wyłączone"}.get(state, state)
        return f"{friendly}: {status}"

    return f"{friendly}: {state}"


class HomeAssistantClient:
    """Komunikuje się z REST API jedynej, globalnej instancji Home Assistant."""

    def __init__(self, base_url: str, access_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def list_devices(self) -> list[Device]:
        url = f"{self.base_url}/api/states"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()
                entities = response.json()
        except Exception as e:
            logger.error(f"Nie udało się pobrać listy encji z Home Assistant [{self.base_url}]: {e}")
            return []

        devices: list[Device] = []
        for entity in entities:
            entity_id = entity.get("entity_id", "")
            if "." not in entity_id:
                continue
            domain = entity_id.split(".", 1)[0]
            attributes = entity.get("attributes", {})
            devices.append(
                Device(
                    id=entity_id,
                    name=attributes.get("friendly_name", entity_id),
                    kind=domain,
                    capabilities=_capabilities_for_entity(domain, attributes),
                    area=attributes.get("area_id"),
                )
            )
        return devices

    async def _call_service(
        self, domain: str, service: str, entity_id: str, extra: dict[str, Any] | None = None
    ) -> ToolResult:
        url = f"{self.base_url}/api/services/{domain}/{service}"
        payload: dict[str, Any] = {"entity_id": entity_id, **(extra or {})}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Błąd wywołania usługi '{service}' na encji '{entity_id}' w Home Assistant: {e}")
            return ToolResult(is_error=True, content=f"Nie udało się wykonać akcji: {e}")
        return ToolResult(content="")

    async def invoke(self, entity_id: str, capability: str, **kwargs: Any) -> ToolResult:
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""

        if capability == "get_state":
            url = f"{self.base_url}/api/states/{entity_id}"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, headers=self._headers())
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:
                logger.error(f"Błąd odczytu stanu encji '{entity_id}' z Home Assistant: {e}")
                return ToolResult(is_error=True, content=f"Nie udało się odczytać stanu urządzenia: {e}")
            text = _format_state_text(entity_id, domain, data.get("state", "unknown"), data.get("attributes", {}))
            return ToolResult(content=text)

        if capability == "turn_off":
            result = await self._call_service(domain, "turn_off", entity_id)
            if result.is_error:
                return result
            return ToolResult(content="Pomyślnie wyłączono urządzenie.")

        if capability == "turn_on":
            extra: dict[str, Any] = {}
            if kwargs.get("brightness_pct") is not None:
                extra["brightness"] = round(kwargs["brightness_pct"] * 255 / 100)
            if kwargs.get("color_temp_kelvin") is not None:
                extra["color_temp_kelvin"] = kwargs["color_temp_kelvin"]
            if kwargs.get("rgb_color") is not None:
                extra["rgb_color"] = kwargs["rgb_color"]
            if kwargs.get("effect") is not None:
                extra["effect"] = kwargs["effect"]
            result = await self._call_service(domain, "turn_on", entity_id, extra)
            if result.is_error:
                return result
            suffix = " Zaktualizowano ustawienia światła." if extra else ""
            return ToolResult(content=f"Pomyślnie włączono urządzenie.{suffix}")

        return ToolResult(is_error=True, content=f"Nieobsługiwana akcja: '{capability}'.")

    async def test_connection(self) -> tuple[bool, str]:
        """Testuje połączenie i zwraca (ok, komunikat czytelny dla użytkownika).

        Rozróżnia najczęstsze przyczyny niepowodzenia (zły token vs zły adres
        vs serwer nieosiągalny) zamiast zwracać gołe `bool` — użytkownik
        konfigurujący połączenie potrzebuje wiedzieć CO poprawić.
        """
        url = f"{self.base_url}/api/config"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=self._headers())
        except httpx.TimeoutException:
            return False, "Przekroczono czas oczekiwania — sprawdź adres serwera."
        except Exception as e:
            return False, f"Nie udało się połączyć z serwerem: {e}"

        if response.status_code == 401:
            return False, "Błąd autoryzacji (401) — sprawdź token dostępu."
        if response.status_code == 403:
            return False, "Brak uprawnień (403) — token nie ma wymaganego dostępu."
        if response.status_code != 200:
            return False, f"Błąd połączenia (HTTP {response.status_code})."

        try:
            version = response.json().get("version", "")
        except Exception:
            version = ""
        message = f"Połączono: Home Assistant {version}".strip() if version else "Połączono z Home Assistant."
        return True, message

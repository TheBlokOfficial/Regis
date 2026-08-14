# Dodawanie nowej integracji Smart Home

Ten dokument opisuje, jak dodać nową integrację (Warstwa 2) do pluginu
`SmartHomePlugin` (Warstwa 1), na bazie faktycznie zaimplementowanego kodu —
`services/server/src/server/integrations/home_assistant.py` jako referencyjny
przykład i `services/server/src/server/plugins/smart_home/contract.py` jako
kontrakt, który trzeba spełnić.

> Ten dokument dotyczy wyłącznie integracji w obrębie **istniejącego**
> pluginu Smart Home. Dodawanie zupełnie nowego pluginu (nowej domeny
> możliwości agenta, nie kolejnej integracji smart home) to osobny temat —
> patrz `docs/manifest.md`, sekcja 5, punkt 2.

---

## 1. Kontrakt do zaimplementowania: `DeviceIntegration`

`services/server/src/server/plugins/smart_home/contract.py`:

```python
class DeviceIntegration(ABC):
    @abstractmethod
    async def list_devices(self) -> list[Device]: ...

    @abstractmethod
    async def invoke(self, device_id: str, capability: str, **kwargs: Any) -> ToolResult: ...

    async def check_health(self) -> bool:
        return True
```

To jest **cała** powierzchnia, jaką integracja musi zaimplementować. Nie ma
tu żadnego miejsca na definiowanie własnych narzędzi LLM — narzędzia rdzenia
(`get_state`/`turn_on`/`turn_off`) implementuje raz plugin
(`smart_home/tools.py`), współdzielone przez wszystkie zarejestrowane
integracje. Nazwa i opis narzędzia nigdy nie ujawniają, która integracja
stoi za konkretnym urządzeniem.

`Device` (`smart_home/models.py`) to model, na którym operuje plugin:

```python
@dataclass
class Device:
    id: str                       # natywny ID w Twojej integracji (bez namespace'u — plugin go doda)
    integration_id: str           # zostaw "" — plugin wypełni po zwrocie z list_devices()
    name: str                     # przyjazna nazwa widoczna dla agenta/użytkownika
    kind: str                     # kategoria (np. 'light', 'switch', 'climate', 'sensor')
    capabilities: set[str]        # podzbiór {'turn_on', 'turn_off', 'get_state'} — nazwy narzędzi, które to urządzenie obsługuje
    area: str | None = None       # opcjonalny, luźny tag lokalizacji (bez rejestru)
```

`capabilities` to zbiór **nazw narzędzi rdzenia**, jakie dane urządzenie
obsługuje — plugin sprawdza to przy wykonaniu (`SmartHomeToolExecutor`) i
odmawia wywołania narzędzia, którego urządzenie nie deklaruje.

---

## 2. `list_devices()` — katalog urządzeń

Zwraca listę `Device` z **natywnymi** identyfikatorami (bez żadnego
namespace'u integracji) — plugin sam nada im przestrzeń nazw
(`{integration_instance_id}:{native_id}`) zaraz po zwrocie, w
`SmartHomePlugin.build()`. Zostaw `integration_id=""`.

Przykład z `HomeAssistantIntegration.list_devices()` — pobranie encji z REST
API i zmapowanie na `Device`, z funkcją pomocniczą wyliczającą capabilities
na podstawie domeny encji HA:

```python
_TOGGLEABLE_DOMAINS = {"light", "switch", "fan", "input_boolean"}

def _capabilities_for_domain(domain: str) -> set[str]:
    if domain in _TOGGLEABLE_DOMAINS:
        return {"turn_on", "turn_off", "get_state"}
    return {"get_state"}

async def list_devices(self) -> list[Device]:
    entities = ...  # GET {base_url}/api/states
    devices = []
    for entity in entities:
        domain = entity["entity_id"].split(".", 1)[0]
        devices.append(Device(
            id=entity["entity_id"],
            integration_id="",
            name=entity["attributes"].get("friendly_name", entity["entity_id"]),
            kind=domain,
            capabilities=_capabilities_for_domain(domain),
            area=entity["attributes"].get("area_id"),
        ))
    return devices
```

Błędy sieciowe/API loguj i zwracaj pustą listę (`[]`) — jedna niedostępna
integracja nie może wywalić budowania kontekstu całego pluginu (`build()`
kontynuuje z pozostałymi włączonymi integracjami, logując błąd per
integracja).

---

## 3. `invoke()` — wykonanie akcji

```python
async def invoke(self, device_id: str, capability: str, **kwargs: Any) -> ToolResult:
```

- `device_id` — **natywny** ID (plugin już zdjął namespace zanim wywołał
  `invoke()` — patrz `SmartHomeToolExecutor._invoke_device` w
  `smart_home/tools.py`, `device.id.split(":", 1)[1]`).
- `capability` — jedna z nazw narzędzi rdzenia (`"get_state"`, `"turn_on"`,
  `"turn_off"`), zawsze taka, którą to urządzenie zadeklarowało w
  `capabilities` (plugin sprawdza to przed wywołaniem `invoke()`).
- Zwróć `ToolResult(content=...)` przy sukcesie, `ToolResult(is_error=True, content=...)`
  przy błędzie — treść trafia bezpośrednio do LLM, więc powinna być
  czytelnym, zwięzłym opisem stanu/wyniku, nie surowym JSON-em API.

Przykład (`HomeAssistantIntegration.invoke`, uproszczone):

```python
async def invoke(self, device_id: str, capability: str, **kwargs: Any) -> ToolResult:
    domain = device_id.split(".", 1)[0]
    if capability == "get_state":
        data = await self._get(f"/api/states/{device_id}")
        return ToolResult(content=_format_state_text(device_id, domain, data["state"], data["attributes"]))
    if capability in ("turn_on", "turn_off"):
        await self._post(f"/api/services/{domain}/{capability}", json={"entity_id": device_id})
        return ToolResult(content=f"Pomyślnie {'włączono' if capability == 'turn_on' else 'wyłączono'} urządzenie.")
    return ToolResult(is_error=True, content=f"Nieobsługiwana akcja: '{capability}'.")
```

Nie dodawaj nowych `capability` poza `get_state`/`turn_on`/`turn_off` —
plugin nie zdefiniuje dla nich narzędzia LLM, więc `invoke()` nigdy nie
zostanie z nimi wywołane. Rozszerzenie zestawu narzędzi rdzenia (np. o
sterowanie jasnością) wymaga zmiany `smart_home/tools.py`, nie samej
integracji.

---

## 4. `check_health()` (opcjonalne)

Domyślna implementacja zwraca zawsze `True`. Nadpisz, jeśli integracja ma
tani sposób sprawdzenia dostępności (np. ping do API):

```python
async def check_health(self) -> bool:
    try:
        response = await self._get("/api/")
        return response.status_code == 200
    except Exception:
        return False
```

---

## 5. Rejestracja typu integracji

Moduł integracji eksportuje trzy nazwy na poziomie modułu — kompletny zestaw
danych do samorejestracji, bez żadnej wiedzy pluginu o Tobie na sztywno:

```python
TYPE_NAME = "MY_INTEGRATION"

SCHEMA = ProviderTypeSpecDTO(
    type=TYPE_NAME,
    label="Moja integracja",
    options_schema=[
        ProviderOptionSpec(name="base_url", label="Adres serwera", type="string", required=True, ...),
        ProviderOptionSpec(name="access_token", label="Token dostępu", type="password", required=True, ...),
    ],
)

def create(options: dict[str, Any]) -> MyIntegration:
    return MyIntegration(base_url=options["base_url"], access_token=options["access_token"])
```

`type="password"` w `ProviderOptionSpec` sprawia, że wartość jest maskowana
w odpowiedziach REST (`_mask_secret_options` w `network/routes/integrations.py`)
— użyj go dla każdego sekretu (tokeny, hasła, klucze API).

Zarejestruj w `main.py`, obok istniejącej integracji Home Assistant:

```python
smart_home_plugin.register_integration_type(my_integration.TYPE_NAME, my_integration.create, my_integration.SCHEMA)
```

Od tego momentu instancję integracji można utworzyć przez REST
(`POST /api/v1/integrations` z `"type": "MY_INTEGRATION"`) — CRUD, walidacja
i persystencja w plikach JSON są już gotowe w `SmartHomePlugin`, nic więcej
nie trzeba pisać.

---

## 6. Czego **nie** robić

- Nie importuj niczego z `server.agent` (kernel) ani `server.plugins.smart_home.plugin`
  — integracja zna wyłącznie kontrakt (`contract.py`) i model (`models.py`).
- Nie próbuj rozwiązywać grup urządzeń — to w pełni wewnętrzna sprawa
  pluginu (`smart_home/plugin.py`, `build()`), integracja nigdy nie widzi
  pojęcia grupy.
- Nie generuj ani nie interpretuj opaque `entity_id` — to wyłącznie sprawa
  Gateway (`server/agent/gateway.py`). Integracja zawsze dostaje i zwraca
  natywne identyfikatory.
- Nie dodawaj własnych narzędzi LLM w integracji — jeśli potrzebujesz nowego
  narzędzia dla całej domeny smart home (nie tylko swojej integracji),
  rozszerz `smart_home/tools.py` w pluginie.

---

## 7. Weryfikacja

1. `python -m uv run python -m pytest -q` — istniejące testy
   (`services/server/tests/test_agent_tools.py`) pokrywają capability gating,
   delegację do integracji i częściowy sukces grup na poziomie
   `SmartHomeToolExecutor` — napisz analogiczny test z `FakeIntegration`
   dla nowej logiki, jeśli dodajesz coś ponad prosty REST client.
2. Zarejestruj integrację w `main.py`, uruchom serwer
   (`python -m uv run --package server python -m server.main`), utwórz
   instancję przez `POST /api/v1/integrations`, włącz ją (`enabled: true`)
   i porozmawiaj z agentem — encja Twojej integracji powinna pojawić się w
   kanale Encji (widoczna w logach/promptcie jako `[<opaque_id>] <nazwa>`).

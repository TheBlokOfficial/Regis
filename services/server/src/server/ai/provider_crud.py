"""Logika CRUD instancji dostawcy — wspólna dla LLM, STT i TTS.

Trzy routery REST (`network/routes/providers.py` oraz dwa bloki w
`voice/provider_routes.py`) były swoimi kopiami: ta sama lista/aktywacja/
tworzenie/edycja/usuwanie, ta sama walidacja typu, to samo maskowanie pól
sekretnych i ta sama reguła „pominięty sekret zachowuje obecną wartość".
Same funkcje maskowania istniały w kodzie **trzykrotnie**
(`network/routes/providers.py`, `voice/provider_routes.py`, plus wariant
`_mask_token` w `world/api/mappers.py`).

Ten moduł **nie zna HTTP** — rzuca zwykłe wyjątki domenowe, a tłumaczenie ich na
kody odpowiedzi zostaje w routerach, które jako jedyne wiedzą, jaki status pasuje
do której operacji. Dzięki temu CRUD da się przetestować bez podnoszenia FastAPI,
a `server.ai` nie zaczyna zależeć od warstwy transportowej.

Zwracane są **słowniki**, nie DTO: kształt pól (`id`/`type`/`name`/`options`/
`is_active`) jest we wszystkich trzech domenach identyczny, ale klasy DTO zostają
osobne (`LLMProviderDTO`/`STTProviderDTO`/`TTSProviderDTO`) — ich scalenie
zmieniłoby nazwy schematów w OpenAPI, a to jedyna rzecz, którą ten etap ma
zostawić nietkniętą.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Type

from shared import ProviderMetadataResponse

from server.ai.provider_registry import ProviderRegistry

SchemasProvider = Callable[[], ProviderMetadataResponse]
"""`{LLM,STT,TTS}Factory.get_all_schemas` — Single Source of Truth pól formularza,
z której wyprowadzamy też, które pola są sekretne."""

ProviderPayload = dict[str, Any]
"""`{id, type, name, options, is_active}` — surowe pola DTO, przed opakowaniem
w klasę właściwą dla domeny."""


class ProviderNotFoundError(LookupError):
    """Instancja o podanym ID nie istnieje."""


class UnsupportedProviderTypeError(ValueError):
    """Żądany typ dostawcy nie należy do enuma tej domeny."""


class ProviderCrud:
    """Operacje na kolekcji instancji dostawcy, wspólne dla wszystkich trzech domen."""

    def __init__(
        self,
        registry: ProviderRegistry[Any, Any, Any],
        schemas_provider: SchemasProvider,
        type_enum: Type[Enum],
        label: str,
    ) -> None:
        """:param label: nazwa domeny w komunikatach błędów ("LLM", "STT", "TTS")."""
        self._registry = registry
        self._schemas_provider = schemas_provider
        self._type_enum = type_enum
        self._label = label

    # --------------------------------------------------------------------------
    # Pola sekretne — jedno źródło prawdy dla maskowania i dla zachowywania wartości
    # --------------------------------------------------------------------------

    def _secret_field_names(self, provider_type: str) -> set[str]:
        """Pola oznaczone w schemacie dostawcy jako `password`. Ten sam schemat, z którego
        frontend renderuje formularz — więc maskowanie nie może rozjechać się z UI."""
        return {
            spec.name
            for type_spec in self._schemas_provider().provider_types
            if type_spec.type == provider_type
            for spec in type_spec.options_schema
            if spec.type == "password"
        }

    def mask_secrets(self, provider_type: str, options: dict[str, Any]) -> dict[str, Any]:
        """Zamienia wartości pól sekretnych na kropki z czterema ostatnimi znakami.

        Klucze API nie powinny nigdy opuszczać serwera w czystym tekście przez REST."""
        secret_fields = self._secret_field_names(provider_type)
        if not secret_fields:
            return options
        masked = dict(options)
        for field_name in secret_fields:
            value = masked.get(field_name)
            if isinstance(value, str) and value:
                masked[field_name] = mask_secret_value(value)
        return masked

    def merge_preserving_secrets(
        self, provider_type: str, existing: dict[str, Any], incoming: dict[str, Any]
    ) -> dict[str, Any]:
        """Pole sekretne puste/pominięte w żądaniu **zachowuje** obecną wartość.

        Frontend nigdy nie zna prawdziwego klucza (GET zwraca go zamaskowanego), więc
        nie ma czego odesłać — bez tej reguły każdy zapis formularza edycji nadpisywałby
        klucz ciągiem kropek."""
        merged = dict(incoming)
        for field_name in self._secret_field_names(provider_type):
            if not str(merged.get(field_name, "")).strip():
                if field_name in existing:
                    merged[field_name] = existing[field_name]
                else:
                    merged.pop(field_name, None)
        return merged

    # --------------------------------------------------------------------------
    # Operacje
    # --------------------------------------------------------------------------

    async def list_payloads(self) -> tuple[list[ProviderPayload], str]:
        """Wszystkie instancje (z zamaskowanymi sekretami) oraz ID aktywnej."""
        instances = await self._registry.load_all_instances()
        active_id = await self._registry.get_active_backend_id()
        payloads = [self._to_payload(cfg, active_id) for cfg in instances.values()]
        return payloads, active_id

    async def activate(self, provider_id: str) -> None:
        """:raises ProviderNotFoundError: gdy instancja nie istnieje."""
        if provider_id not in await self._registry.load_all_instances():
            raise ProviderNotFoundError(f"Dostawca {self._label} o ID '{provider_id}' nie istnieje.")
        await self._registry.set_active_backend_id(provider_id)

    async def create(
        self, type_str: str, name: str, options: dict[str, Any], custom_id: str | None
    ) -> ProviderPayload:
        """:raises UnsupportedProviderTypeError: gdy typ nie należy do enuma domeny.
        :raises ValueError: gdy `custom_id` nie jest bezpieczną nazwą pliku."""
        created = await self._registry.create_instance(
            provider_type=self._parse_type(type_str), name=name, options=options, custom_id=custom_id
        )
        return self._to_payload(created, await self._registry.get_active_backend_id())

    async def update(self, provider_id: str, name: str | None, options: dict[str, Any]) -> ProviderPayload:
        """Edycja nazwy i opcji; typ jest niezmienny (patrz `ProviderRegistry.update_instance`).

        :raises ProviderNotFoundError: gdy instancja nie istnieje."""
        existing = (await self._registry.load_all_instances()).get(provider_id)
        if existing is None:
            raise ProviderNotFoundError(f"Dostawca {self._label} o ID '{provider_id}' nie istnieje.")
        type_str = _type_to_str(existing.type)
        merged = self.merge_preserving_secrets(type_str, existing.options, options)
        updated = await self._registry.update_instance(provider_id, name, merged)
        return self._to_payload(updated, await self._registry.get_active_backend_id())

    async def delete(self, provider_id: str) -> None:
        """:raises ProviderNotFoundError: gdy instancja nie istnieje.
        :raises ValueError: przy próbie usunięcia aktywnej instancji."""
        if not await self._registry.delete_instance(provider_id):
            raise ProviderNotFoundError(f"Dostawca {self._label} o ID '{provider_id}' nie istnieje.")

    # --------------------------------------------------------------------------

    def _parse_type(self, type_str: str) -> Enum:
        try:
            return self._type_enum(type_str.upper())
        except ValueError as err:
            supported = ", ".join(t.value for t in self._type_enum)
            raise UnsupportedProviderTypeError(
                f"Niewspierany typ dostawcy {self._label}: '{type_str}'. Dozwolone: {supported}."
            ) from err

    def _to_payload(self, config: Any, active_id: str) -> ProviderPayload:
        type_str = _type_to_str(config.type)
        return {
            "id": config.id,
            "type": type_str,
            "name": config.name,
            "options": self.mask_secrets(type_str, config.options),
            "is_active": config.id == active_id,
        }


def _type_to_str(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def mask_secret_value(value: str) -> str:
    """Kropki + cztery ostatnie znaki. Wydzielone, bo tej samej maski używa
    `world/api/mappers.py` dla tokenu Home Assistant — jedyne miejsce poza dostawcami AI,
    gdzie sekret opuszcza serwer w postaci podglądowej."""
    visible = value[-4:] if len(value) > 4 else ""
    return f"{'•' * (len(value) - len(visible))}{visible}"

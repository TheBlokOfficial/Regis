"""Referencje sekretów `env:NAZWA` (`shared/secrets.py`).

Mechanizm ma dwie własności, których złamanie jest ciche i kosztowne:

* **rozwiązana wartość nie może wyciec poza granicę budowy dostawcy** — `load_all_instances()`
  zasila warstwę REST i CRUD, więc gdyby rozwiązywała referencje, prawdziwy klucz
  wychodziłby z serwera przy każdym `GET /providers`;
* **referencja nie może zostać zamaskowana** — maska zabrałaby jedyny sygnał, że
  instancja bierze klucz ze środowiska, i użytkownik nie miałby jak tego zdiagnozować.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from server.ai.llm.models import ProviderType
from server.ai.llm.registry import BackendRegistry
from server.ai.provider_crud import ProviderCrud
from shared import ProviderMetadataResponse, ProviderOptionSpec, ProviderTypeSpecDTO, resolve_secret, resolve_secret_refs


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ------------------------------------------------------------------------------
# Rozwiązywanie
# ------------------------------------------------------------------------------


def test_literal_value_passes_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Istniejące klucze wpisane wprost działają dalej — nie ma czego migrować."""
    monkeypatch.setenv("REGIS_TEST_KEY", "nie ta wartość")

    assert resolve_secret("gsk_prawdziwy_klucz") == "gsk_prawdziwy_klucz"
    assert resolve_secret("") == ""


def test_reference_is_resolved_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGIS_TEST_KEY", "gsk_ze_srodowiska")

    assert resolve_secret("env:REGIS_TEST_KEY") == "gsk_ze_srodowiska"
    assert resolve_secret("  env:REGIS_TEST_KEY  ") == "gsk_ze_srodowiska"


def test_missing_variable_degrades_to_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Łagodna degradacja, nie wyjątek: jedna źle skonfigurowana instancja spośród kilku
    nie może wywrócić startu serwera. Dostawca odrzuci żądanie, a przyczyna będzie
    widoczna w zakładce Logi."""
    monkeypatch.delenv("REGIS_TEST_BRAK", raising=False)

    assert resolve_secret("env:REGIS_TEST_BRAK") == ""
    assert resolve_secret("env:") == ""


def test_only_referenced_values_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rozwiązywanie nie potrzebuje wiedzy o tym, które pole jest sekretne — prefiks
    wystarcza, więc jedna funkcja obsługuje worek opcji dowolnego dostawcy."""
    monkeypatch.setenv("REGIS_TEST_KEY", "sekret")
    options = {"model": "gpt-oss-120b", "api_key": "env:REGIS_TEST_KEY", "temperature": "0.2", "retries": 3}

    resolved = resolve_secret_refs(options)

    assert resolved == {"model": "gpt-oss-120b", "api_key": "sekret", "temperature": "0.2", "retries": 3}
    # Oryginał nietknięty — rozwiązana postać nie może wrócić do magazynu
    assert options["api_key"] == "env:REGIS_TEST_KEY"


# ------------------------------------------------------------------------------
# Granica: rejestr rozwiązuje przy budowie, nie przy odczycie
# ------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_registry_resolves_only_when_building_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGIS_TEST_KEY", "gsk_prawdziwy")
    registry = BackendRegistry(data_dir=tmp_path)
    created = await registry.create_instance(
        provider_type=ProviderType.GROQ,
        name="Groq (ze środowiska)",
        options={"api_key": "env:REGIS_TEST_KEY", "model": "openai/gpt-oss-120b"},
    )

    # 1. Odczyt z magazynu zwraca postać NIEROZWIĄZANĄ — to on zasila REST i CRUD
    instances = await registry.load_all_instances()
    assert instances[created.id].options["api_key"] == "env:REGIS_TEST_KEY"

    # 2. Dopiero budowa konkretu podstawia prawdziwą wartość
    captured: dict[str, str] = {}

    def fake_create(config: object) -> str:
        captured.update(config.options)  # type: ignore[attr-defined]
        return "provider"

    monkeypatch.setattr(registry, "_create_provider", fake_create)
    registry.build_provider(instances[created.id])

    assert captured["api_key"] == "gsk_prawdziwy"
    # 3. ...i nie mutuje instancji trzymanej w pamięci
    assert instances[created.id].options["api_key"] == "env:REGIS_TEST_KEY"


# ------------------------------------------------------------------------------
# Maskowanie
# ------------------------------------------------------------------------------


def _crud_with_secret_field() -> ProviderCrud:
    schemas = ProviderMetadataResponse(
        provider_types=[
            ProviderTypeSpecDTO(
                type="GROQ",
                label="Groq",
                options_schema=[ProviderOptionSpec(name="api_key", label="Klucz API", type="password")],
            )
        ]
    )
    return ProviderCrud(
        registry=None,  # type: ignore[arg-type]
        schemas_provider=lambda: schemas,
        type_enum=ProviderType,
        label="LLM",
    )


def test_literal_secret_is_masked_but_reference_is_not() -> None:
    crud = _crud_with_secret_field()

    masked = crud.mask_secrets("GROQ", {"api_key": "gsk_abcdefgh1234"})
    passthrough = crud.mask_secrets("GROQ", {"api_key": "env:REGIS_GROQ_KONTAKT"})

    assert masked["api_key"].endswith("1234")
    assert "•" in masked["api_key"]
    assert passthrough["api_key"] == "env:REGIS_GROQ_KONTAKT"


def test_reference_survives_edit_without_being_retyped() -> None:
    """Frontend odsyła referencję taką, jaką dostał (nie jest zamaskowana), więc reguła
    „puste pole = zachowaj obecną wartość" nie ma tu nic do roboty i nie może jej zjeść."""
    crud = _crud_with_secret_field()

    merged = crud.merge_preserving_secrets(
        "GROQ", existing={"api_key": "env:STARA"}, incoming={"api_key": "env:NOWA"}
    )
    kept = crud.merge_preserving_secrets("GROQ", existing={"api_key": "env:STARA"}, incoming={"api_key": ""})

    assert merged["api_key"] == "env:NOWA"
    assert kept["api_key"] == "env:STARA"

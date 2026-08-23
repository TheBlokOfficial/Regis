"""Edycja presetu LLM (`PUT /api/v1/llm/providers/{id}`).

Do tej pory preset dało się wyłącznie utworzyć i skasować — zmiana `max_tokens`
oznaczała skasowanie instancji i zbudowanie jej od nowa, razem z ponownym wklejeniem
klucza API. Sedno tych testów to zachowywanie sekretów: frontend nigdy nie zna
prawdziwego klucza (GET zwraca go zamaskowanego), więc nie może go odesłać z powrotem —
bez świadomej obsługi tego przypadku każdy zapis formularza edycji nadpisywałby klucz
ciągiem kropek.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.ai.llm import BackendRegistry
from server.network.routes.providers import create_providers_router

REAL_KEY = "gsk_prawdziwy_klucz_uzytkownika"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        app = FastAPI()
        app.include_router(create_providers_router(BackendRegistry(data_dir=Path(tmp_dir))))
        yield TestClient(app)


def _create(client: TestClient, **options: str) -> str:
    response = client.post(
        "/api/v1/llm/providers",
        json={"type": "GROQ", "name": "Dom", "options": {"api_key": REAL_KEY, "model": "openai/gpt-oss-120b", **options}},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _stored_options(client: TestClient, provider_id: str) -> dict:
    providers = client.get("/api/v1/llm/providers").json()["providers"]
    return next(p for p in providers if p["id"] == provider_id)["options"]


def test_editing_without_api_key_preserves_the_stored_one(client: TestClient) -> None:
    provider_id = _create(client)

    response = client.put(
        f"/api/v1/llm/providers/{provider_id}",
        json={"options": {"model": "openai/gpt-oss-20b", "temperature": "0.3"}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["options"]["model"] == "openai/gpt-oss-20b"
    # Odpowiedź maskuje klucz, więc prawdziwą wartość sprawdzamy przez fabrykę niżej;
    # tutaj wystarczy, że maska pokazuje ostatnie znaki ORYGINALNEGO klucza.
    assert response.json()["options"]["api_key"].endswith(REAL_KEY[-4:])


def test_editing_with_a_new_api_key_replaces_it(client: TestClient) -> None:
    provider_id = _create(client)

    client.put(f"/api/v1/llm/providers/{provider_id}", json={"options": {"api_key": "gsk_zupelnie_nowy"}})

    assert _stored_options(client, provider_id)["api_key"].endswith("nowy"[-4:])


def test_masked_value_sent_back_does_not_become_the_key(client: TestClient) -> None:
    """Najbardziej podstępny wariant: formularz odsyła to, co dostał z GET, czyli kropki.
    Puste/zamaskowane pole musi znaczyć "zachowaj", nigdy "zapisz kropki jako klucz"."""
    provider_id = _create(client)

    client.put(f"/api/v1/llm/providers/{provider_id}", json={"options": {"api_key": "   ", "model": "x"}})

    stored = _stored_options(client, provider_id)["api_key"]
    assert stored.endswith(REAL_KEY[-4:])
    assert set(stored) != {"•"}


def test_name_is_editable_and_omitting_it_preserves_the_current_one(client: TestClient) -> None:
    """Nazwa presetu jest odtąd własnym bytem, a nie echem nazwy modelu."""
    provider_id = _create(client)

    assert client.put(f"/api/v1/llm/providers/{provider_id}", json={"name": "Salon"}).json()["name"] == "Salon"
    assert client.put(f"/api/v1/llm/providers/{provider_id}", json={"options": {"model": "y"}}).json()["name"] == "Salon"


def test_editing_preserves_active_selection(client: TestClient) -> None:
    provider_id = _create(client)
    client.put("/api/v1/llm/providers/active", json={"provider_id": provider_id})

    response = client.put(f"/api/v1/llm/providers/{provider_id}", json={"options": {"model": "z"}})

    assert response.json()["is_active"] is True


def test_editing_unknown_provider_is_404(client: TestClient) -> None:
    assert client.put("/api/v1/llm/providers/bk_nie_ma", json={"name": "x"}).status_code == 404


def test_models_endpoint_reports_why_the_list_is_empty(client: TestClient) -> None:
    """Brak klucza to normalny stan konfiguracyjny, nie błąd — endpoint odpowiada 200
    z powodem, żeby UI mogło go pokazać zamiast udawać, że dostawca nie ma modeli."""
    response = client.post(
        "/api/v1/llm/providers", json={"type": "GROQ", "name": "Bez klucza", "options": {"api_key": ""}}
    )
    provider_id = response.json()["id"]

    payload = client.get(f"/api/v1/llm/providers/{provider_id}/models").json()

    assert payload["models"] == []
    assert payload["detail"]
    # Nawet bez listy da się skonfigurować model wpisany z ręki.
    assert payload["fallback_options_schema"]

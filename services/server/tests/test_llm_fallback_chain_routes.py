"""REST łańcucha fallbacku LLM (`GET/PUT /api/v1/llm/backends/fallback-chain`).

Mechanika samego `LLMRouter` jest przetestowana w `test_ai_routers.py` (fake
registry) — tu sprawdzamy wyłącznie transport i walidację REST-ową na
prawdziwym `BackendRegistry` (pliki JSON w katalogu tymczasowym), mirror
`test_llm_provider_editing.py`."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.ai.llm import BackendRegistry
from server.network.routes.providers import create_providers_router


@pytest.fixture
def client() -> Iterator[TestClient]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        app = FastAPI()
        app.include_router(create_providers_router(BackendRegistry(data_dir=Path(tmp_dir))))
        yield TestClient(app)


def _create(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/llm/providers", json={"type": "GROQ", "name": name, "options": {}})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_default_chain_is_empty(client: TestClient) -> None:
    assert client.get("/api/v1/llm/backends/fallback-chain").json()["priority_ids"] == []


def test_set_and_get_chain_round_trips(client: TestClient) -> None:
    first = _create(client, "Groq klucz 1")
    second = _create(client, "OpenRouter")

    response = client.put("/api/v1/llm/backends/fallback-chain", json={"priority_ids": [first, second]})

    assert response.status_code == 200, response.text
    assert response.json()["priority_ids"] == [first, second]
    assert client.get("/api/v1/llm/backends/fallback-chain").json()["priority_ids"] == [first, second]


def test_setting_chain_with_unknown_id_is_400(client: TestClient) -> None:
    response = client.put("/api/v1/llm/backends/fallback-chain", json={"priority_ids": ["bk_nie_istnieje"]})

    assert response.status_code == 400


def test_empty_chain_can_be_saved_to_clear_it(client: TestClient) -> None:
    first = _create(client, "Groq klucz 1")
    client.put("/api/v1/llm/backends/fallback-chain", json={"priority_ids": [first]})

    response = client.put("/api/v1/llm/backends/fallback-chain", json={"priority_ids": []})

    assert response.json()["priority_ids"] == []


def test_deleting_a_provider_prunes_it_from_the_saved_chain() -> None:
    """Regresja na żywo: usunięcie presetu figurującego w łańcuchu zostawiało martwy
    ID w `fallback_chain.json` na zawsze. Pierwsza kolejna edycja priorytetu ZUPEŁNIE
    INNEGO presetu (przez UI) odsyłała ten martwy ID z powrotem — `set_fallback_chain`
    odrzuca cały zapis, gdy choć jeden ID jest nieznany, więc psuło to edycję presetu,
    który nigdy nie był ruszany."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        app = FastAPI()
        app.include_router(create_providers_router(BackendRegistry(data_dir=Path(tmp_dir))))
        client = TestClient(app)

        first = _create(client, "Groq klucz 1")
        second = _create(client, "OpenRouter")
        client.put("/api/v1/llm/backends/fallback-chain", json={"priority_ids": [first, second]})

        assert client.delete(f"/api/v1/llm/providers/{first}").status_code == 200

        assert client.get("/api/v1/llm/backends/fallback-chain").json()["priority_ids"] == [second]
        # Edycja pozostałego presetu (dokładając go z powrotem w tej samej kolejności)
        # musi się udać — wcześniej 400-owała przez martwy ID pierwszego presetu.
        response = client.put("/api/v1/llm/backends/fallback-chain", json={"priority_ids": [second]})
        assert response.status_code == 200, response.text

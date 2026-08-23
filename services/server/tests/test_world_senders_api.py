"""`POST /api/v1/world/senders` — jedno wejście do rejestru klientów, obsługujące trzy
różne intencje o różnej wiedzy o kliencie.

Nadawcę zapisują dziś trzy miejsca UI, każde znające inny wycinek jego profilu:
zakładka Klienci zna możliwości z handshake i nadaje nazwę, zakładka Świat zna tylko
pokój. Skoro wszystkie wołają ten sam upsert, brakujące pole musi znaczyć "zachowaj",
inaczej każdy zapis po cichu kasowałby cudzą pracę. Wyjątkiem jest `room_id`: tam
`None` to legalne "— brak pokoju —" z pickera, więc ta semantyka go nie obejmuje.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.world.engine import WorldEngine
from server.world.routes import create_world_router

SENDER = "snd_desktop_1"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        app = FastAPI()
        app.include_router(
            create_world_router(WorldEngine(data_dir=Path(tmp_dir) / "world")), prefix="/api/v1/world"
        )
        yield TestClient(app)


def _register(client: TestClient, **payload: object) -> dict:
    response = client.post("/api/v1/world/senders", json={"sender_id": SENDER, **payload})
    assert response.status_code == 201, response.text
    return response.json()


def test_display_name_defaults_to_empty(client: TestClient) -> None:
    """Nazwa nie jest generowana automatycznie — UI fallbackuje do skróconego ID,
    zamiast zostawiać w liście generyczne "Klient 1" do końca świata."""
    assert _register(client)["display_name"] is None


def test_display_name_is_saved_and_returned(client: TestClient) -> None:
    _register(client)

    assert _register(client, display_name="Salon — satelita")["display_name"] == "Salon — satelita"
    assert client.get("/api/v1/world/senders").json()[0]["display_name"] == "Salon — satelita"


def test_room_change_from_world_tab_preserves_name(client: TestClient) -> None:
    """Picker pokoju w zakładce Świat nic o nazwie nie wie i jej nie wysyła — pominięte
    pole musi znaczyć "zachowaj", inaczej każda zmiana pokoju kasowałaby nazwę."""
    _register(client, display_name="Kuchnia")
    room_id = client.post("/api/v1/world/rooms", json={"name": "Kuchnia"}).json()["id"]

    updated = _register(client, room_id=room_id)

    assert updated["display_name"] == "Kuchnia"
    assert updated["room_id"] == room_id


def test_empty_display_name_clears_it(client: TestClient) -> None:
    """Wyczyszczenie nazwy jest osobną, jawną intencją (pusty string), odróżnialną od
    "nie wiem nic o nazwie" (pominięte pole)."""
    _register(client, display_name="Do usunięcia")

    assert _register(client, display_name="")["display_name"] is None


def test_whitespace_only_display_name_is_treated_as_empty(client: TestClient) -> None:
    _register(client, display_name="   ")

    assert client.get("/api/v1/world/senders").json()[0]["display_name"] is None


def test_rename_preserves_capabilities(client: TestClient) -> None:
    """Zmiana nazwy z zakładki Klienci nie może zgubić możliwości — bez nich World
    zbudowałby tekstowe ramowanie odpowiedzi dla klienta z głośnikiem."""
    _register(client, capabilities=["mic", "speaker"])

    renamed = _register(client, display_name="Sypialnia")

    assert set(renamed["capabilities"]) == {"mic", "speaker"}


def test_room_can_still_be_cleared(client: TestClient) -> None:
    """`room_id: null` zostaje realnym "brak pokoju" — semantyka "zachowaj" dotyczy
    wyłącznie nazwy i możliwości."""
    room_id = client.post("/api/v1/world/rooms", json={"name": "Salon"}).json()["id"]
    _register(client, room_id=room_id)

    assert _register(client, room_id=None)["room_id"] is None

"""Konfiguracja połączenia z Home Assistant i surowy katalog encji."""

from __future__ import annotations

from fastapi import APIRouter

from server.world.api.mappers import to_config_dto
from server.world.dto import (
    CatalogEntryDTO,
    HomeAssistantConfigDTO,
    TestConnectionResponse,
    TestHAConnectionRequest,
    UpdateHomeAssistantConfigRequest,
)
from server.world.engine import WorldEngine


def create_router(engine: WorldEngine) -> APIRouter:
    router = APIRouter()

    @router.get("/config", response_model=HomeAssistantConfigDTO, tags=["World"])
    async def get_config() -> HomeAssistantConfigDTO:
        return to_config_dto(await engine.get_config())

    @router.put("/config", response_model=HomeAssistantConfigDTO, tags=["World"])
    async def update_config(req: UpdateHomeAssistantConfigRequest) -> HomeAssistantConfigDTO:
        return to_config_dto(await engine.save_config(base_url=req.base_url, access_token=req.access_token))

    @router.post("/config/test", response_model=TestConnectionResponse, tags=["World"])
    async def test_config(req: TestHAConnectionRequest) -> TestConnectionResponse:
        ok, message = await engine.test_connection(base_url=req.base_url, access_token=req.access_token)
        return TestConnectionResponse(ok=ok, message=message)

    @router.get("/catalog", response_model=list[CatalogEntryDTO], tags=["World"])
    async def get_catalog() -> list[CatalogEntryDTO]:
        """Surowy katalog WSZYSTKICH encji HA — do wyszukiwarki w UI, nie to, co widzi
        agent (ten widzi wyłącznie listę zadeklarowaną, patrz `devices.py`).

        Jedyny endpoint Świata kosztujący żywe zapytanie HTTP do fizycznego Home
        Assistanta, stąd w UI dociągany leniwie, przy pierwszym kontakcie z polem
        wyszukiwania — nie przy wejściu w zakładkę."""
        devices = await engine.get_catalog()
        return [CatalogEntryDTO(entity_id=d.id, friendly_name=d.name, kind=d.kind, ha_area=d.area) for d in devices]

    return router

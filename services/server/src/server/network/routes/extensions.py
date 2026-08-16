"""Generyczny rejestr rozszerzeń — jedyna treść współdzielona między nimi
(kształt „lista rozszerzeń", nigdy domena żadnego z nich).
"""

from fastapi import APIRouter, HTTPException, status
from shared import ExtensionListResponse, ExtensionSummaryDTO, SetExtensionEnabledRequest

from server.network.extension_contract import NetworkExtension


def create_extensions_registry_router(extensions: list[NetworkExtension]) -> APIRouter:
    """Tworzy router z absolutnymi ścieżkami dla listy i przełącznika rozszerzeń."""
    router = APIRouter()

    @router.get(
        "/api/v1/extensions",
        response_model=ExtensionListResponse,
        summary="Pobiera listę zarejestrowanych rozszerzeń i ich stan enabled",
        tags=["Extensions"],
    )
    async def list_extensions() -> ExtensionListResponse:
        return ExtensionListResponse(
            extensions=[
                ExtensionSummaryDTO(id=ext.extension_id, label=ext.label, enabled=await ext.is_enabled())
                for ext in extensions
            ]
        )

    @router.put(
        "/api/v1/extensions/{extension_id}",
        response_model=ExtensionSummaryDTO,
        summary="Włącza/wyłącza rozszerzenie",
        tags=["Extensions"],
    )
    async def set_extension_enabled(extension_id: str, req: SetExtensionEnabledRequest) -> ExtensionSummaryDTO:
        ext = next((e for e in extensions if e.extension_id == extension_id), None)
        if ext is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rozszerzenie '{extension_id}' nie istnieje.")
        await ext.set_enabled(req.enabled)
        return ExtensionSummaryDTO(id=ext.extension_id, label=ext.label, enabled=req.enabled)

    return router

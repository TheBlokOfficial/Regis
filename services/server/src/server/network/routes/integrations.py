from typing import Any
from fastapi import APIRouter, HTTPException, status
from shared import (
    CreateDeviceGroupRequest,
    CreateIntegrationRequest,
    DeviceGroupDTO,
    DeviceGroupListResponse,
    IntegrationDTO,
    IntegrationListResponse,
    ProviderMetadataResponse,
    UpdateDeviceGroupRequest,
    UpdateIntegrationRequest,
)
from server.addons.smart_home import SmartHomeAddon


def _mask_secret_options(smart_home_addon: SmartHomeAddon, provider_type: str, options: dict[str, Any]) -> dict[str, Any]:
    """Maskuje wartości pól oznaczonych w schemacie jako 'password' (np. access_token).

    Ten sam mechanizm co dla dostawców LLM (`routes/providers.py`) — sekrety
    nigdy nie opuszczają serwera w czystym tekście przez API REST. Schemat
    pochodzi z faktycznie zarejestrowanych w addonie typów integracji, nie
    z listy zaszytej na sztywno.
    """
    secret_fields = {
        spec.name
        for type_spec in smart_home_addon.get_all_schemas().provider_types
        if type_spec.type == provider_type
        for spec in type_spec.options_schema
        if spec.type == "password"
    }
    if not secret_fields:
        return options

    masked = dict(options)
    for field_name in secret_fields:
        value = masked.get(field_name)
        if isinstance(value, str) and value:
            visible = value[-4:] if len(value) > 4 else ""
            masked[field_name] = f"{'•' * (len(value) - len(visible))}{visible}"
    return masked


def create_integrations_router(smart_home_addon: SmartHomeAddon) -> APIRouter:
    """Tworzy router dla punktów końcowych konfiguracji dostawców i grup addonu Smart Home."""
    router = APIRouter()

    # --------------------------------------------------------------------------
    # Integracje (np. Home Assistant) — typy pochodzą z tego co zarejestrowano
    # jawnie w main.py, addon nie zna żadnej z góry.
    # --------------------------------------------------------------------------

    @router.get(
        "/api/v1/integrations/schemas",
        response_model=ProviderMetadataResponse,
        summary="Pobiera generyczne specyfikacje pól opcji dla dostępnych typów integracji",
        tags=["Integrations"],
    )
    async def get_integration_schemas() -> ProviderMetadataResponse:
        return smart_home_addon.get_all_schemas()

    @router.get(
        "/api/v1/integrations",
        response_model=IntegrationListResponse,
        summary="Pobiera listę skonfigurowanych integracji",
        tags=["Integrations"],
    )
    async def get_integrations() -> IntegrationListResponse:
        instances = await smart_home_addon.list_integration_instances()
        integrations_dto = [
            IntegrationDTO(
                id=cfg.id,
                type=cfg.type,
                name=cfg.name,
                options=_mask_secret_options(smart_home_addon, cfg.type, cfg.options),
                enabled=cfg.enabled,
            )
            for cfg in instances.values()
        ]
        return IntegrationListResponse(integrations=integrations_dto)

    @router.post(
        "/api/v1/integrations",
        response_model=IntegrationDTO,
        status_code=status.HTTP_201_CREATED,
        summary="Tworzy nową instancję integracji i zapisuje plik JSON",
        tags=["Integrations"],
    )
    async def create_integration(req: CreateIntegrationRequest) -> IntegrationDTO:
        try:
            created_cfg = await smart_home_addon.create_integration_instance(
                provider_type=req.type.upper(),
                name=req.name,
                options=req.options,
                enabled=req.enabled,
                custom_id=req.custom_id,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

        return IntegrationDTO(
            id=created_cfg.id,
            type=created_cfg.type,
            name=created_cfg.name,
            options=_mask_secret_options(smart_home_addon, created_cfg.type, created_cfg.options),
            enabled=created_cfg.enabled,
        )

    @router.put(
        "/api/v1/integrations/{integration_id}",
        response_model=IntegrationDTO,
        summary="Aktualizuje instancję integracji (w tym włączenie/wyłączenie)",
        tags=["Integrations"],
    )
    async def update_integration(integration_id: str, req: UpdateIntegrationRequest) -> IntegrationDTO:
        try:
            updated_cfg = await smart_home_addon.update_integration_instance(
                provider_id=integration_id,
                name=req.name,
                options=req.options,
                enabled=req.enabled,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

        return IntegrationDTO(
            id=updated_cfg.id,
            type=updated_cfg.type,
            name=updated_cfg.name,
            options=_mask_secret_options(smart_home_addon, updated_cfg.type, updated_cfg.options),
            enabled=updated_cfg.enabled,
        )

    @router.delete(
        "/api/v1/integrations/{integration_id}",
        summary="Usuwa plik instancji integracji z dysku",
        tags=["Integrations"],
    )
    async def delete_integration(integration_id: str):
        deleted = await smart_home_addon.delete_integration_instance(integration_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Integracja o ID '{integration_id}' nie istnieje.",
            )
        return {"success": True, "deleted_id": integration_id}

    # --------------------------------------------------------------------------
    # Grupy urządzeń
    # --------------------------------------------------------------------------

    @router.get(
        "/api/v1/integrations/groups",
        response_model=DeviceGroupListResponse,
        summary="Pobiera listę skonfigurowanych grup urządzeń",
        tags=["Device Groups"],
    )
    async def get_groups() -> DeviceGroupListResponse:
        instances = await smart_home_addon.list_groups()
        return DeviceGroupListResponse(
            groups=[DeviceGroupDTO(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids) for cfg in instances.values()]
        )

    @router.post(
        "/api/v1/integrations/groups",
        response_model=DeviceGroupDTO,
        status_code=status.HTTP_201_CREATED,
        summary="Tworzy nową grupę urządzeń",
        tags=["Device Groups"],
    )
    async def create_group(req: CreateDeviceGroupRequest) -> DeviceGroupDTO:
        created_cfg = await smart_home_addon.create_group(
            name=req.name,
            device_ids=req.device_ids,
            custom_id=req.custom_id,
        )
        return DeviceGroupDTO(id=created_cfg.id, name=created_cfg.name, device_ids=created_cfg.device_ids)

    @router.put(
        "/api/v1/integrations/groups/{group_id}",
        response_model=DeviceGroupDTO,
        summary="Aktualizuje grupę urządzeń",
        tags=["Device Groups"],
    )
    async def update_group(group_id: str, req: UpdateDeviceGroupRequest) -> DeviceGroupDTO:
        try:
            updated_cfg = await smart_home_addon.update_group(
                group_id=group_id,
                name=req.name,
                device_ids=req.device_ids,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        return DeviceGroupDTO(id=updated_cfg.id, name=updated_cfg.name, device_ids=updated_cfg.device_ids)

    @router.delete(
        "/api/v1/integrations/groups/{group_id}",
        summary="Usuwa grupę urządzeń z dysku",
        tags=["Device Groups"],
    )
    async def delete_group(group_id: str):
        deleted = await smart_home_addon.delete_group(group_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grupa o ID '{group_id}' nie istnieje.",
            )
        return {"success": True, "deleted_id": group_id}

    return router

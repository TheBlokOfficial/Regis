"""Router REST CRUD dla dostawców STT/TTS (`ai.stt`/`ai.tts`) — mirror
`network/routes/providers.py` (LLM). Montowany osobno od `voice/routes.py`
(status/connected), pod tym samym prefiksem `/api/v1/voice`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from shared import ProviderMetadataResponse

from server.ai.stt import STTFactory, STTProviderType, STTRegistry
from server.ai.tts import TTSFactory, TTSProviderType, TTSRegistry
from server.voice.dto import (
    CreateSTTProviderRequest,
    CreateTTSProviderRequest,
    SelectSTTProviderRequest,
    SelectTTSProviderRequest,
    STTProviderDTO,
    STTProviderListResponse,
    TTSProviderDTO,
    TTSProviderListResponse,
    UpdateProviderRequest,
)


def _mask_secret_options(schemas: ProviderMetadataResponse, provider_type: str, options: dict[str, Any]) -> dict[str, Any]:
    """Maskuje pola oznaczonych w schemacie jako 'password' — mirror
    `network/routes/providers.py::_mask_secret_options`, reużyty dla STT/TTS."""
    secret_fields = {
        spec.name
        for type_spec in schemas.provider_types
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


def _merge_preserving_secrets(
    schemas: ProviderMetadataResponse, provider_type: str, existing: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Pole sekretne puste/pominięte w żądaniu **zachowuje** obecną wartość — frontend
    nigdy nie zna prawdziwego klucza (GET maskuje go kropkami), więc nie mógłby go
    odesłać. Mirror `network/routes/providers.py::_merge_preserving_secrets`."""
    secret_fields = {
        spec.name
        for type_spec in schemas.provider_types
        if type_spec.type == provider_type
        for spec in type_spec.options_schema
        if spec.type == "password"
    }
    merged = dict(incoming)
    for field_name in secret_fields:
        if not str(merged.get(field_name, "")).strip():
            if field_name in existing:
                merged[field_name] = existing[field_name]
            else:
                merged.pop(field_name, None)
    return merged


def create_voice_providers_router(stt_registry: STTRegistry, tts_registry: TTSRegistry) -> APIRouter:
    """Tworzy router dla CRUD dostawców STT/TTS."""
    router = APIRouter()

    # -- STT ------------------------------------------------------------------

    @router.get("/stt/providers/schemas", response_model=ProviderMetadataResponse, tags=["STT Providers"])
    async def get_stt_provider_schemas() -> ProviderMetadataResponse:
        return STTFactory.get_all_schemas()

    @router.get("/stt/providers", response_model=STTProviderListResponse, tags=["STT Providers"])
    async def get_stt_providers() -> STTProviderListResponse:
        instances = await stt_registry.load_all_instances()
        active_id = await stt_registry.get_active_backend_id()
        schemas = STTFactory.get_all_schemas()

        providers_dto = [
            STTProviderDTO(
                id=cfg.id,
                type=cfg.type.value,
                name=cfg.name,
                options=_mask_secret_options(schemas, cfg.type.value, cfg.options),
                is_active=(cfg.id == active_id),
            )
            for cfg in instances.values()
        ]
        return STTProviderListResponse(providers=providers_dto, active_id=active_id)

    @router.put("/stt/providers/active", response_model=STTProviderListResponse, tags=["STT Providers"])
    async def set_active_stt_provider(req: SelectSTTProviderRequest) -> STTProviderListResponse:
        all_instances = await stt_registry.load_all_instances()
        if req.provider_id not in all_instances:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dostawca STT o ID '{req.provider_id}' nie istnieje.",
            )
        await stt_registry.set_active_backend_id(req.provider_id)
        return await get_stt_providers()

    @router.post(
        "/stt/providers", response_model=STTProviderDTO, status_code=status.HTTP_201_CREATED, tags=["STT Providers"]
    )
    async def create_stt_provider(req: CreateSTTProviderRequest) -> STTProviderDTO:
        try:
            p_type = STTProviderType(req.type.upper())
        except ValueError:
            supported = ", ".join(t.value for t in STTProviderType)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Niewspierany typ dostawcy STT: '{req.type}'. Dozwolone: {supported}.",
            ) from None
        try:
            created_cfg = await stt_registry.create_instance(
                provider_type=p_type, name=req.name, options=req.options, custom_id=req.custom_id
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

        active_id = await stt_registry.get_active_backend_id()
        schemas = STTFactory.get_all_schemas()
        return STTProviderDTO(
            id=created_cfg.id,
            type=created_cfg.type.value,
            name=created_cfg.name,
            options=_mask_secret_options(schemas, created_cfg.type.value, created_cfg.options),
            is_active=(created_cfg.id == active_id),
        )

    @router.put("/stt/providers/{provider_id}", response_model=STTProviderDTO, tags=["STT Providers"])
    async def update_stt_provider(provider_id: str, req: UpdateProviderRequest) -> STTProviderDTO:
        instances = await stt_registry.load_all_instances()
        existing = instances.get(provider_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Dostawca STT o ID '{provider_id}' nie istnieje."
            )
        schemas = STTFactory.get_all_schemas()
        merged = _merge_preserving_secrets(schemas, existing.type.value, existing.options, req.options)
        updated = await stt_registry.update_instance(provider_id, merged, req.name)
        active_id = await stt_registry.get_active_backend_id()
        return STTProviderDTO(
            id=updated.id,
            type=updated.type.value,
            name=updated.name,
            options=_mask_secret_options(schemas, updated.type.value, updated.options),
            is_active=(updated.id == active_id),
        )

    @router.delete("/stt/providers/{provider_id}", tags=["STT Providers"])
    async def delete_stt_provider(provider_id: str):
        try:
            deleted = await stt_registry.delete_instance(provider_id)
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dostawca STT o ID '{provider_id}' nie istnieje.",
                )
            return {"success": True, "deleted_id": provider_id}
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

    # -- TTS ------------------------------------------------------------------

    @router.get("/tts/providers/schemas", response_model=ProviderMetadataResponse, tags=["TTS Providers"])
    async def get_tts_provider_schemas() -> ProviderMetadataResponse:
        return TTSFactory.get_all_schemas()

    @router.get("/tts/providers", response_model=TTSProviderListResponse, tags=["TTS Providers"])
    async def get_tts_providers() -> TTSProviderListResponse:
        instances = await tts_registry.load_all_instances()
        active_id = await tts_registry.get_active_backend_id()
        schemas = TTSFactory.get_all_schemas()

        providers_dto = [
            TTSProviderDTO(
                id=cfg.id,
                type=cfg.type.value,
                name=cfg.name,
                options=_mask_secret_options(schemas, cfg.type.value, cfg.options),
                is_active=(cfg.id == active_id),
            )
            for cfg in instances.values()
        ]
        return TTSProviderListResponse(providers=providers_dto, active_id=active_id)

    @router.put("/tts/providers/active", response_model=TTSProviderListResponse, tags=["TTS Providers"])
    async def set_active_tts_provider(req: SelectTTSProviderRequest) -> TTSProviderListResponse:
        all_instances = await tts_registry.load_all_instances()
        if req.provider_id not in all_instances:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dostawca TTS o ID '{req.provider_id}' nie istnieje.",
            )
        await tts_registry.set_active_backend_id(req.provider_id)
        return await get_tts_providers()

    @router.post(
        "/tts/providers", response_model=TTSProviderDTO, status_code=status.HTTP_201_CREATED, tags=["TTS Providers"]
    )
    async def create_tts_provider(req: CreateTTSProviderRequest) -> TTSProviderDTO:
        try:
            p_type = TTSProviderType(req.type.upper())
        except ValueError:
            supported = ", ".join(t.value for t in TTSProviderType)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Niewspierany typ dostawcy TTS: '{req.type}'. Dozwolone: {supported}.",
            ) from None
        try:
            created_cfg = await tts_registry.create_instance(
                provider_type=p_type, name=req.name, options=req.options, custom_id=req.custom_id
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

        active_id = await tts_registry.get_active_backend_id()
        schemas = TTSFactory.get_all_schemas()
        return TTSProviderDTO(
            id=created_cfg.id,
            type=created_cfg.type.value,
            name=created_cfg.name,
            options=_mask_secret_options(schemas, created_cfg.type.value, created_cfg.options),
            is_active=(created_cfg.id == active_id),
        )

    @router.put("/tts/providers/{provider_id}", response_model=TTSProviderDTO, tags=["TTS Providers"])
    async def update_tts_provider(provider_id: str, req: UpdateProviderRequest) -> TTSProviderDTO:
        instances = await tts_registry.load_all_instances()
        existing = instances.get(provider_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Dostawca TTS o ID '{provider_id}' nie istnieje."
            )
        schemas = TTSFactory.get_all_schemas()
        merged = _merge_preserving_secrets(schemas, existing.type.value, existing.options, req.options)
        updated = await tts_registry.update_instance(provider_id, merged, req.name)
        active_id = await tts_registry.get_active_backend_id()
        return TTSProviderDTO(
            id=updated.id,
            type=updated.type.value,
            name=updated.name,
            options=_mask_secret_options(schemas, updated.type.value, updated.options),
            is_active=(updated.id == active_id),
        )

    @router.delete("/tts/providers/{provider_id}", tags=["TTS Providers"])
    async def delete_tts_provider(provider_id: str):
        try:
            deleted = await tts_registry.delete_instance(provider_id)
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dostawca TTS o ID '{provider_id}' nie istnieje.",
                )
            return {"success": True, "deleted_id": provider_id}
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

    return router

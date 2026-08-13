from typing import Any
from fastapi import APIRouter, HTTPException, status
from shared import (
    CreateLLMProviderRequest,
    LLMProviderDTO,
    LLMProviderListResponse,
    ProviderMetadataResponse,
    SelectLLMProviderRequest,
)
from server.agent import AgentEngine
from server.agent.backend import BackendRegistry, ProviderType
from server.agent.backend.factory import LLMFactory


def _mask_secret_options(provider_type: str, options: dict[str, Any]) -> dict[str, Any]:
    """Maskuje wartości pól oznaczonych w schemacie dostawcy jako 'password' (np. api_key).

    Klucze API nie powinny nigdy opuszczać serwera w czystym tekście przez API REST —
    pola sekretne są rozpoznawane na podstawie tego samego schematu, którego używa
    frontend do renderowania formularzy (LLMFactory.get_all_schemas(), Single Source of Truth).
    """
    secret_fields = {
        spec.name
        for type_spec in LLMFactory.get_all_schemas().provider_types
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


def create_providers_router(
    backend_registry: BackendRegistry,
    agent_engine: AgentEngine,
) -> APIRouter:
    """Tworzy router dla punktów końcowych konfiguracji dostawców LLM."""
    router = APIRouter()

    @router.get(
        "/api/v1/llm/providers/schemas",
        response_model=ProviderMetadataResponse,
        summary="Pobiera generyczne specyfikacje pól opcji dla dostępnych typów dostawców LLM",
        tags=["LLM Providers"],
    )
    async def get_llm_provider_schemas() -> ProviderMetadataResponse:
        return LLMFactory.get_all_schemas()

    @router.get(
        "/api/v1/llm/providers",
        response_model=LLMProviderListResponse,
        summary="Pobiera listę skonfigurowanych dostawców LLM oraz ID aktywnego",
        tags=["LLM Providers"],
    )
    async def get_llm_providers() -> LLMProviderListResponse:
        instances = await backend_registry.load_all_instances()
        active_id = await backend_registry.get_active_backend_id()

        providers_dto = []
        for cfg in instances.values():
            type_str = cfg.type.value if hasattr(cfg.type, "value") else str(cfg.type)
            providers_dto.append(
                LLMProviderDTO(
                    id=cfg.id,
                    type=type_str,
                    name=cfg.name,
                    options=_mask_secret_options(type_str, cfg.options),
                    is_active=(cfg.id == active_id),
                )
            )

        return LLMProviderListResponse(providers=providers_dto, active_id=active_id)

    @router.put(
        "/api/v1/llm/providers/active",
        response_model=LLMProviderListResponse,
        summary="Wybiera i przełącza aktywnego dostawcę LLM w agencie",
        tags=["LLM Providers"],
    )
    async def set_active_llm_provider(req: SelectLLMProviderRequest) -> LLMProviderListResponse:
        all_instances = await backend_registry.load_all_instances()
        if req.provider_id not in all_instances:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dostawca LLM o ID '{req.provider_id}' nie istnieje.",
            )

        await backend_registry.set_active_backend_id(req.provider_id)
        agent_engine.llm_provider = await backend_registry.get_active_provider()

        return await get_llm_providers()

    @router.post(
        "/api/v1/llm/providers",
        response_model=LLMProviderDTO,
        status_code=status.HTTP_201_CREATED,
        summary="Tworzy nową instancję dostawcy LLM i zapisuje plik JSON",
        tags=["LLM Providers"],
    )
    async def create_llm_provider(req: CreateLLMProviderRequest) -> LLMProviderDTO:
        try:
            p_type = ProviderType(req.type.upper())
        except ValueError:
            supported = ", ".join(t.value for t in ProviderType)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Niewspierany typ dostawcy LLM: '{req.type}'. Dozwolone: {supported}.",
            )

        try:
            created_cfg = await backend_registry.create_instance(
                provider_type=p_type,
                name=req.name,
                options=req.options,
                custom_id=req.custom_id,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

        active_id = await backend_registry.get_active_backend_id()
        type_str = created_cfg.type.value if hasattr(created_cfg.type, "value") else str(created_cfg.type)

        return LLMProviderDTO(
            id=created_cfg.id,
            type=type_str,
            name=created_cfg.name,
            options=_mask_secret_options(type_str, created_cfg.options),
            is_active=(created_cfg.id == active_id),
        )

    @router.delete(
        "/api/v1/llm/providers/{provider_id}",
        summary="Usuwa plik instancji dostawcy LLM z dysku",
        tags=["LLM Providers"],
    )
    async def delete_llm_provider(provider_id: str):
        try:
            deleted = await backend_registry.delete_instance(provider_id)
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dostawca LLM o ID '{provider_id}' nie istnieje.",
                )
            return {"success": True, "deleted_id": provider_id}
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            )

    return router

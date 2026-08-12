from fastapi import APIRouter, HTTPException, status
import shared
from shared import (
    CreateLLMProviderRequest,
    HealthResponse,
    LLMProviderDTO,
    LLMProviderListResponse,
    ProviderMetadataResponse,
    SelectLLMProviderRequest,
)
from server.agent import AgentEngine
from server.agent.backend import BackendRegistry, ProviderType
from server.agent.backend.factory import LLMFactory


def create_api_router(
    agent_engine: AgentEngine,
    backend_registry: BackendRegistry,
) -> APIRouter:
    """Centralny rejestr używanych punktów końcowych REST API serwera Regis OS."""
    router = APIRouter()

    # 1. GET /api/health
    @router.get(
        "/api/health",
        response_model=HealthResponse,
        summary="Status zdrowia serwera centralnego",
        tags=["System"],
    )
    async def health() -> HealthResponse:
        return HealthResponse(
            system="Regis Agent OS",
            gateway_status="online",
            agent_engine_status="ready",
            shared_version=shared.__version__,
        )

    # 2. GET /api/llm/providers/schemas
    @router.get(
        "/api/llm/providers/schemas",
        response_model=ProviderMetadataResponse,
        summary="Pobiera generyczne specyfikacje pól opcji dla dostępnych typów dostawców LLM",
        tags=["LLM Providers"],
    )
    async def get_llm_provider_schemas() -> ProviderMetadataResponse:
        return LLMFactory.get_all_schemas()

    # 3. GET /api/llm/providers
    @router.get(
        "/api/llm/providers",
        response_model=LLMProviderListResponse,
        summary="Pobiera listę skonfigurowanych dostawców LLM oraz ID aktywnego",
        tags=["LLM Providers"],
    )
    async def get_llm_providers() -> LLMProviderListResponse:
        instances = await backend_registry.load_all_instances()
        active_id = await backend_registry.get_active_backend_id()

        providers_dto = [
            LLMProviderDTO(
                id=cfg.id,
                type=cfg.type.value if hasattr(cfg.type, "value") else str(cfg.type),
                name=cfg.name,
                options=cfg.options,
                is_active=(cfg.id == active_id),
            )
            for cfg in instances.values()
        ]

        return LLMProviderListResponse(providers=providers_dto, active_id=active_id)

    # 4. PUT /api/llm/providers/active
    @router.put(
        "/api/llm/providers/active",
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

    # 5. POST /api/llm/providers
    @router.post(
        "/api/llm/providers",
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

        created_cfg = await backend_registry.create_instance(
            provider_type=p_type,
            name=req.name,
            options=req.options,
            custom_id=req.custom_id,
        )

        active_id = await backend_registry.get_active_backend_id()

        return LLMProviderDTO(
            id=created_cfg.id,
            type=created_cfg.type.value if hasattr(created_cfg.type, "value") else str(created_cfg.type),
            name=created_cfg.name,
            options=created_cfg.options,
            is_active=(created_cfg.id == active_id),
        )

    # 6. DELETE /api/llm/providers/{provider_id}
    @router.delete(
        "/api/llm/providers/{provider_id}",
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

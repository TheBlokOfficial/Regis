import json
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import shared
from shared import (
    CancelChatApiRequest,
    ChatResponseDTO,
    ChatSessionHistoryResponse,
    ChatSessionListResponse,
    ChatSessionSummaryDTO,
    CreateLLMProviderRequest,
    HealthResponse,
    LLMProviderDTO,
    LLMProviderListResponse,
    ProviderMetadataResponse,
    SelectLLMProviderRequest,
    SendChatMessageRequest,
)
from server.agent import AgentEngine
from server.agent.backend import BackendRegistry, ProviderType
from server.agent.backend.factory import LLMFactory


class CreateSessionApiRequest(BaseModel):
    """Żądanie utrwalenia nowej sesji przez API."""

    title: str = Field(default="Nowa konwersacja", description="Tytuł nowej sesji")
    custom_id: str | None = Field(default=None, description="Opcjonalne własne ID sesji (np. session_custom)")


def create_api_router(
    agent_engine: AgentEngine,
    backend_registry: BackendRegistry,
) -> APIRouter:
    """Centralny rejestr używanych punktów końcowych REST i SSE API serwera Regis OS."""
    router = APIRouter()

    # 1. GET /api/v1/health
    @router.get(
        "/api/v1/health",
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

    # 2. GET /api/v1/llm/providers/schemas
    @router.get(
        "/api/v1/llm/providers/schemas",
        response_model=ProviderMetadataResponse,
        summary="Pobiera generyczne specyfikacje pól opcji dla dostępnych typów dostawców LLM",
        tags=["LLM Providers"],
    )
    async def get_llm_provider_schemas() -> ProviderMetadataResponse:
        return LLMFactory.get_all_schemas()

    # 3. GET /api/v1/llm/providers
    @router.get(
        "/api/v1/llm/providers",
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

    # 4. PUT /api/v1/llm/providers/active
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

    # 5. POST /api/v1/llm/providers
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

    # 6. DELETE /api/v1/llm/providers/{provider_id}
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

    # ==========================================================================
    # CHAT & SESSIONS ENDPOINTS (AGENT OS MULTI-SESSION CONVERSATIONS)
    # ==========================================================================

    # 7. POST /api/v1/chat
    @router.post(
        "/api/v1/chat",
        response_model=ChatResponseDTO,
        summary="Wysyła wiadomość do Agenta i zwraca pełną odpowiedź w jednym żądaniu",
        tags=["Chat & Sessions"],
    )
    async def chat_interact(req: SendChatMessageRequest) -> ChatResponseDTO:
        if agent_engine.is_session_busy(req.session_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sesja '{req.session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.",
            )
        try:
            return await agent_engine.interact(
                session_id=req.session_id,
                prompt=req.message,
                system_prompt=req.system_prompt,
            )
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Błąd generowania odpowiedzi przez Agenta: {err}",
            )

    # 8. POST /api/v1/chat/stream
    @router.post(
        "/api/v1/chat/stream",
        summary="Wysyła wiadomość do Agenta i strumieniuje odpowiedź w czasie rzeczywistym via SSE",
        tags=["Chat & Sessions"],
    )
    async def chat_interact_stream(req: SendChatMessageRequest):
        if agent_engine.is_session_busy(req.session_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sesja '{req.session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.",
            )

        async def event_generator():
            try:
                async for chunk in agent_engine.interact_stream(
                    session_id=req.session_id,
                    prompt=req.message,
                    system_prompt=req.system_prompt,
                ):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as err:
                error_payload = json.dumps({"error": str(err)})
                yield f"data: {error_payload}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 8b. POST /api/v1/chat/cancel
    @router.post(
        "/api/v1/chat/cancel",
        summary="Anuluje aktywne generowanie odpowiedzi dla podanej sesji (Web, Satelita, Cron)",
        tags=["Chat & Sessions"],
    )
    async def cancel_chat_interact(req: CancelChatApiRequest):
        cancelled = await agent_engine.cancel_interaction(req.session_id)
        return {"success": cancelled, "session_id": req.session_id}

    # 9. GET /api/v1/chat/sessions
    @router.get(
        "/api/v1/chat/sessions",
        response_model=ChatSessionListResponse,
        summary="Pobiera listę wszystkich aktywnych i zapisanych sesji konwersacji z backendu",
        tags=["Chat & Sessions"],
    )
    async def get_chat_sessions() -> ChatSessionListResponse:
        summaries = agent_engine.memory_manager.list_session_summaries()
        return ChatSessionListResponse(sessions=summaries)

    # 10. POST /api/v1/chat/sessions
    @router.post(
        "/api/v1/chat/sessions",
        response_model=ChatSessionSummaryDTO,
        status_code=status.HTTP_201_CREATED,
        summary="Tworzy nową sesję konwersacji w pamięci i na dysku",
        tags=["Chat & Sessions"],
    )
    async def create_chat_session(req: CreateSessionApiRequest) -> ChatSessionSummaryDTO:
        session = agent_engine.memory_manager.create_session(
            title=req.title,
            custom_id=req.custom_id,
        )
        return session.to_summary()

    # 11. GET /api/v1/chat/sessions/{session_id}/history
    @router.get(
        "/api/v1/chat/sessions/{session_id}/history",
        response_model=ChatSessionHistoryResponse,
        summary="Pobiera pełną historię wiadomości oraz metadane konkretnej sesji",
        tags=["Chat & Sessions"],
    )
    async def get_chat_session_history(session_id: str) -> ChatSessionHistoryResponse:
        session = agent_engine.memory_manager.get_or_create_session(session_id)
        return ChatSessionHistoryResponse(
            session_id=session.session_id,
            title=session.title,
            messages=session.get_history(),
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    # 12. DELETE /api/v1/chat/sessions/{session_id}
    @router.delete(
        "/api/v1/chat/sessions/{session_id}",
        summary="Usuwa historię i plik sesji z dysku serwera",
        tags=["Chat & Sessions"],
    )
    async def delete_chat_session(session_id: str):
        deleted = agent_engine.memory_manager.delete_session(session_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesja o ID '{session_id}' nie istnieje.",
            )
        return {"success": True, "deleted_id": session_id}

    return router

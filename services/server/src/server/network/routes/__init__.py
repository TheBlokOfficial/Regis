from fastapi import APIRouter

from server.agent import AgentEngine
from server.agent.prompts import AgentDefaultPromptStore
from server.ai.llm import BackendRegistry

from .chat import RegistrationCheck, create_chat_router
from .health import create_health_router
from .prompts import create_prompts_router
from .providers import create_providers_router
from .sessions import create_sessions_router


def create_api_router(
    agent_engine: AgentEngine,
    backend_registry: BackendRegistry,
    prompt_store: AgentDefaultPromptStore,
    is_registered: RegistrationCheck | None = None,
) -> APIRouter:
    """Centralny rejestr agregujący zmodularyzowane pod-routery REST i SSE API serwera Regis OS."""
    main_router = APIRouter()

    main_router.include_router(create_health_router())
    main_router.include_router(create_providers_router(backend_registry=backend_registry))
    main_router.include_router(create_chat_router(agent_engine=agent_engine, is_registered=is_registered))
    main_router.include_router(create_sessions_router(agent_engine=agent_engine))
    main_router.include_router(create_prompts_router(prompt_store=prompt_store))

    return main_router


__all__ = [
    "create_api_router",
    "create_health_router",
    "create_prompts_router",
    "create_providers_router",
    "create_chat_router",
    "create_sessions_router",
]

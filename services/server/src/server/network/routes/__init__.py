from fastapi import APIRouter
from server.agent import AgentEngine
from server.agent.backend import BackendRegistry
from server.agent.prompts import PromptStore
from server.addons.smart_home import SmartHomeAddon

from .chat import create_chat_router
from .health import create_health_router
from .integrations import create_integrations_router
from .prompts import create_prompts_router
from .providers import create_providers_router
from .sessions import create_sessions_router


def create_api_router(
    agent_engine: AgentEngine,
    backend_registry: BackendRegistry,
    prompt_store: PromptStore,
    smart_home_addon: SmartHomeAddon | None = None,
) -> APIRouter:
    """Centralny rejestr agregujący zmodularyzowane pod-routery REST i SSE API serwera Regis OS."""
    main_router = APIRouter()

    main_router.include_router(create_health_router())
    main_router.include_router(
        create_providers_router(backend_registry=backend_registry, agent_engine=agent_engine)
    )
    main_router.include_router(create_chat_router(agent_engine=agent_engine))
    main_router.include_router(create_sessions_router(agent_engine=agent_engine))
    main_router.include_router(create_prompts_router(prompt_store=prompt_store))
    main_router.include_router(
        create_integrations_router(smart_home_addon=smart_home_addon or SmartHomeAddon())
    )

    return main_router


__all__ = [
    "create_api_router",
    "create_health_router",
    "create_integrations_router",
    "create_prompts_router",
    "create_providers_router",
    "create_chat_router",
    "create_sessions_router",
]

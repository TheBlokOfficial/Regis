"""Router FastAPI dla fallbackowego promptu systemowego kernela Agenta."""

from fastapi import APIRouter
from shared import AgentDefaultPromptDTO
from server.agent.prompts import AgentDefaultPromptStore


def create_prompts_router(prompt_store: AgentDefaultPromptStore) -> APIRouter:
    """Tworzy router dla fallbackowego promptu systemowego (jedno pole, bez CRUD).

    Używany wyłącznie gdy żaden silnik świata nie dostarcza własnego promptu
    (patrz `agent/context_provider.py`, `ContextBuild.system_prompt`).
    """
    router = APIRouter()

    @router.get(
        "/api/v1/agent/prompt",
        response_model=AgentDefaultPromptDTO,
        summary="Zwraca fallbackowy prompt systemowy kernela",
        tags=["Agent Prompt"],
    )
    async def get_default_prompt() -> AgentDefaultPromptDTO:
        content = await prompt_store.get_content()
        return AgentDefaultPromptDTO(content=content)

    @router.put(
        "/api/v1/agent/prompt",
        response_model=AgentDefaultPromptDTO,
        summary="Aktualizuje fallbackowy prompt systemowy kernela",
        tags=["Agent Prompt"],
    )
    async def update_default_prompt(req: AgentDefaultPromptDTO) -> AgentDefaultPromptDTO:
        await prompt_store.set_content(req.content)
        return AgentDefaultPromptDTO(content=req.content)

    return router

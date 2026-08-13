"""Router FastAPI obsługujący CRUD i zarządzanie aktywnymi promptami systemowymi Agenta."""

from fastapi import APIRouter, HTTPException, status
from shared import (
    CreatePromptRequest,
    PromptDTO,
    PromptListResponse,
    UpdatePromptRequest,
)
from server.agent.prompts import PromptStore


def create_prompts_router(prompt_store: PromptStore) -> APIRouter:
    """Tworzy router dla punktów końcowych zarządzania promptami systemowymi."""
    router = APIRouter()

    @router.get(
        "/api/v1/agent/prompts",
        response_model=PromptListResponse,
        summary="Zwraca listę wszystkich promptów systemowych z flagą aktywnego",
        tags=["Agent Prompts"],
    )
    async def list_prompts() -> PromptListResponse:
        instances = await prompt_store.list_all()
        active_id = await prompt_store.get_active_id()
        prompts = [
            PromptDTO(is_active=(inst.id == active_id), **inst.model_dump())
            for inst in instances
        ]
        return PromptListResponse(prompts=prompts, active_id=active_id)

    @router.post(
        "/api/v1/agent/prompts",
        response_model=PromptDTO,
        status_code=status.HTTP_201_CREATED,
        summary="Tworzy nowy prompt systemowy",
        tags=["Agent Prompts"],
    )
    async def create_prompt(req: CreatePromptRequest) -> PromptDTO:
        try:
            instance = await prompt_store.create(
                name=req.name,
                content=req.content,
                description=req.description,
                custom_id=req.custom_id,
                set_active=req.set_active,
            )
            active_id = await prompt_store.get_active_id()
            return PromptDTO(is_active=(instance.id == active_id), **instance.model_dump())
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    @router.get(
        "/api/v1/agent/prompts/{prompt_id}",
        response_model=PromptDTO,
        summary="Pobiera pojedynczy prompt systemowy po ID",
        tags=["Agent Prompts"],
    )
    async def get_prompt(prompt_id: str) -> PromptDTO:
        try:
            instance = await prompt_store.get(prompt_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt o ID '{prompt_id}' nie istnieje.",
            )
        active_id = await prompt_store.get_active_id()
        return PromptDTO(is_active=(instance.id == active_id), **instance.model_dump())

    @router.put(
        "/api/v1/agent/prompts/{prompt_id}",
        response_model=PromptDTO,
        summary="Aktualizuje pola istniejącego promptu systemowego",
        tags=["Agent Prompts"],
    )
    async def update_prompt(prompt_id: str, req: UpdatePromptRequest) -> PromptDTO:
        try:
            instance = await prompt_store.update(
                prompt_id=prompt_id,
                name=req.name,
                content=req.content,
                description=req.description,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        active_id = await prompt_store.get_active_id()
        return PromptDTO(is_active=(instance.id == active_id), **instance.model_dump())

    @router.delete(
        "/api/v1/agent/prompts/{prompt_id}",
        summary="Usuwa prompt systemowy (blokada aktywnego)",
        tags=["Agent Prompts"],
    )
    async def delete_prompt(prompt_id: str) -> dict:
        try:
            deleted = await prompt_store.delete(prompt_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt o ID '{prompt_id}' nie istnieje.",
            )
        return {"success": True, "prompt_id": prompt_id}

    @router.put(
        "/api/v1/agent/prompts/{prompt_id}/activate",
        response_model=PromptDTO,
        summary="Ustawia wskazany prompt jako aktywny systemowy prompt Agenta",
        tags=["Agent Prompts"],
    )
    async def activate_prompt(prompt_id: str) -> PromptDTO:
        try:
            await prompt_store.set_active(prompt_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        instance = await prompt_store.get(prompt_id)
        return PromptDTO(is_active=True, **instance.model_dump())  # type: ignore[union-attr]

    return router

"""Profile tożsamości Świata — do trzech przełączalnych promptów systemowych.

Treść jest stabilna między turami i trafia na pozycję zerową kontekstu; zmienne
fakty żyją osobno, w sekcjach kontekstu tury (`prompt_sections.py`). Ten podział
wzdłuż osi ZMIENNOŚCI jest świadomy — patrz `docs/manifest.md`, sekcja 5.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from shared import CreatePromptRequest, DeletionResponse, PromptDTO, PromptListResponse, UpdatePromptRequest

from server.world.engine import WorldEngine


def create_router(engine: WorldEngine) -> APIRouter:
    router = APIRouter()

    @router.get("/prompts", response_model=PromptListResponse, tags=["World"])
    async def list_prompts() -> PromptListResponse:
        instances = await engine.list_prompts()
        active_id = await engine.get_active_prompt_id()
        return PromptListResponse(
            prompts=[PromptDTO(is_active=(inst.id == active_id), **inst.model_dump()) for inst in instances],
            active_id=active_id,
        )

    @router.post("/prompts", response_model=PromptDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def create_prompt(req: CreatePromptRequest) -> PromptDTO:
        try:
            instance = await engine.create_prompt(
                name=req.name,
                content=req.content,
                description=req.description,
                custom_id=req.custom_id,
                set_active=req.set_active,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
        active_id = await engine.get_active_prompt_id()
        return PromptDTO(is_active=(instance.id == active_id), **instance.model_dump())

    @router.put("/prompts/{prompt_id}", response_model=PromptDTO, tags=["World"])
    async def update_prompt(prompt_id: str, req: UpdatePromptRequest) -> PromptDTO:
        try:
            instance = await engine.update_prompt(
                prompt_id, name=req.name, content=req.content, description=req.description
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
        active_id = await engine.get_active_prompt_id()
        return PromptDTO(is_active=(instance.id == active_id), **instance.model_dump())

    @router.delete("/prompts/{prompt_id}", response_model=DeletionResponse, tags=["World"])
    async def delete_prompt(prompt_id: str) -> DeletionResponse:
        """Usunięcie aktywnego profilu jest zablokowane (400) — zawsze musi zostać
        co najmniej jeden, inaczej agent straciłby tożsamość w połowie pracy."""
        try:
            deleted = await engine.delete_prompt(prompt_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Profil promptu '{prompt_id}' nie istnieje."
            )
        return DeletionResponse(deleted_id=prompt_id)

    @router.put("/prompts/{prompt_id}/activate", response_model=PromptDTO, tags=["World"])
    async def activate_prompt(prompt_id: str) -> PromptDTO:
        try:
            await engine.set_active_prompt(prompt_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
        instance = await engine.get_prompt(prompt_id)
        if instance is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Profil promptu '{prompt_id}' nie istnieje."
            )
        return PromptDTO(is_active=True, **instance.model_dump())

    return router

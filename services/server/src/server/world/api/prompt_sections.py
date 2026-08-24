"""Sekcje kontekstu tury — edytowalna, uporządkowana lista bloków tekstu.

Kolejność listy jest kolejnością w prompcie, więc `PUT` podmienia ją w całości,
a nie po jednym wpisie. Warunki pochodzą z zamkniętej listy (`CONDITION_SPECS`) —
użytkownik je *wybiera*, nie *pisze*, więc nie ma tu ani sandboxa, ani składni,
w której da się zrobić literówkę.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from server.world.api.mappers import to_sections_response
from server.world.dto import PromptPreviewResponse, PromptSectionsResponse, UpdatePromptSectionsRequest
from server.world.engine import WorldEngine
from server.world.prompt_sections import PromptSection


def create_router(engine: WorldEngine) -> APIRouter:
    router = APIRouter()

    @router.get("/prompt-sections", response_model=PromptSectionsResponse, tags=["World"])
    async def get_prompt_sections() -> PromptSectionsResponse:
        return to_sections_response(await engine.get_prompt_sections())

    @router.put("/prompt-sections", response_model=PromptSectionsResponse, tags=["World"])
    async def update_prompt_sections(req: UpdatePromptSectionsRequest) -> PromptSectionsResponse:
        sections = [
            PromptSection(
                id=dto.id,
                label=dto.label,
                text=dto.text,
                text_negated=dto.text_negated,
                condition=dto.condition,
                condition_param=dto.condition_param,
            )
            for dto in req.sections
        ]
        try:
            config = await engine.save_prompt_sections(sections)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
        return to_sections_response(config)

    @router.post("/prompt-sections/reset", response_model=PromptSectionsResponse, tags=["World"])
    async def reset_prompt_sections() -> PromptSectionsResponse:
        return to_sections_response(await engine.reset_prompt_sections())

    @router.get("/prompt-sections/preview", response_model=PromptPreviewResponse, tags=["World"])
    async def preview_prompt_sections(sender_id: str | None = None) -> PromptPreviewResponse:
        """Podgląd składa się przez `WorldEngine.build()`, czyli DOKŁADNIE tę samą
        ścieżkę co realna tura — łącznie z odpytaniem Home Assistant. Osobna,
        "szybsza" ścieżka renderowania prędzej czy później rozjechałaby się z
        produkcyjną i podgląd przestałby cokolwiek dowodzić."""
        build = await engine.build(sender_id=sender_id)
        return PromptPreviewResponse(turn_context=build.turn_context or "", sender_id=sender_id)

    return router

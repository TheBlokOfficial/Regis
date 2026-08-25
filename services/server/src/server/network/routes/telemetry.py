"""Punkty końcowe podglądu telemetrii wywołań LLM (zakładka „Logi" w Web Console).

Prefiks `telemetry`, nie `logs` — `data/logs/regis.log` to zupełnie inny byt
(tekstowy log aplikacji) i endpoint nie może sugerować, że go serwuje.
"""

from fastapi import APIRouter, HTTPException, Query, status
from shared import GenerationLogDetailDTO, GenerationLogListResponse

from server.telemetry import GenerationLogStore

_MAX_PAGE = 200


def create_telemetry_router(store: GenerationLogStore) -> APIRouter:
    """Tworzy router dla punktów końcowych podglądu zrzutów wywołań LLM."""
    router = APIRouter()

    @router.get(
        "/api/v1/telemetry/generations",
        response_model=GenerationLogListResponse,
        summary="Lista wywołań LLM od najnowszego, stronicowana kursorem `before_id`",
        tags=["Telemetry"],
    )
    async def list_generations(
        limit: int = Query(default=50, ge=1, le=_MAX_PAGE),
        before_id: int | None = Query(default=None, description="Kursor: zwróć wpisy starsze niż ten identyfikator"),
        session_id: str | None = Query(default=None, description="Filtr po sesji czatu"),
        turn_id: str | None = Query(default=None, description="Filtr po jednej turze agenta"),
        generation_status: str | None = Query(
            default=None, alias="status", description="ok | error | cancelled | no_generation"
        ),
    ) -> GenerationLogListResponse:
        return await store.list_entries(
            limit=limit,
            before_id=before_id,
            session_id=session_id,
            turn_id=turn_id,
            status=generation_status,
        )

    @router.get(
        "/api/v1/telemetry/generations/{record_id}",
        response_model=GenerationLogDetailDTO,
        summary="Pełny zrzut jednego wywołania wraz z kontekstem wysłanym do modelu",
        tags=["Telemetry"],
    )
    async def get_generation(record_id: int) -> GenerationLogDetailDTO:
        entry = await store.get_entry(record_id)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Wpis telemetrii '{record_id}' nie istnieje (mógł zostać usunięty przez rotację).",
            )
        return entry

    @router.delete(
        "/api/v1/telemetry/generations",
        summary="Usuwa wszystkie zapisane zrzuty wywołań LLM",
        tags=["Telemetry"],
    )
    async def clear_generations() -> dict[str, int | bool]:
        return {"success": True, "deleted": await store.clear()}

    return router

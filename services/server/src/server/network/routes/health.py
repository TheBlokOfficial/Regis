from fastapi import APIRouter
from shared import HealthResponse
from shared import __version__ as REGIS_VERSION

from server.config import load_settings


def create_health_router() -> APIRouter:
    """Tworzy router dla punktów końcowych statusu zdrowia i systemu."""
    router = APIRouter()

    @router.get(
        "/api/v1/health",
        response_model=HealthResponse,
        summary="Status zdrowia serwera centralnego",
        tags=["System"],
    )
    async def health() -> HealthResponse:
        # `load_settings()` na świeżo przy każdym żądaniu, nie w closure — ten sam
        # wzorzec "instant effect" co w routerach dostawców: zmiana nazwy w pliku
        # konfiguracyjnym jest widoczna bez restartu serwera.
        return HealthResponse(
            app_name=load_settings().app_name,
            gateway_status="online",
            agent_engine_status="ready",
            version=REGIS_VERSION,
        )

    return router

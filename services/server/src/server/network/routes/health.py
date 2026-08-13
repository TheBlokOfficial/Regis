from fastapi import APIRouter
import shared
from shared import HealthResponse


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
        return HealthResponse(
            system="Regis Agent OS",
            gateway_status="online",
            agent_engine_status="ready",
            shared_version=shared.__version__,
        )

    return router

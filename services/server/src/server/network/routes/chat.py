import asyncio
import json
from typing import Awaitable, Callable

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from shared import (
    CancelChatApiRequest,
    ChatResponseDTO,
    SendChatMessageRequest,
)

from server.agent import AgentEngine

RegistrationCheck = Callable[[str], Awaitable[bool]]
"""Czy dany `sender_id` jest zatwierdzonym klientem. Wstrzykiwane z `main.py` (gdzie
implementację dostarcza `World`) — ta warstwa nie importuje `world` i nie wie, skąd
odpowiedź pochodzi; ten sam wzorzec co w `voice/gateway.py`."""


def create_chat_router(agent_engine: AgentEngine, is_registered: RegistrationCheck | None = None) -> APIRouter:
    """Tworzy router dla punktów końcowych interakcji z Agentem."""
    router = APIRouter()

    async def _require_registered(sender_id: str | None) -> None:
        """Bramka rejestracji — ta sama konsekwencja co dla satelit (`voice/session.py`):
        klient musi być zatwierdzony, zanim odpali turę. Nie jest to mechanizm
        bezpieczeństwa (sieć jest zaufana, patrz `docs/manifest.md`), tylko spójność —
        każdy klient wchodzi do systemu tą samą drogą i jest w nim widoczny.

        Brak `sender_id` w żądaniu przechodzi: to wywołania headless (skrypty, cron),
        które nie udają żadnego klienta i nie mają czego rejestrować.
        """
        if is_registered is None or sender_id is None:
            return
        if not await is_registered(sender_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Klient '{sender_id}' nie jest zarejestrowany. Zatwierdź go w Ustawieniach → Klienci.",
            )

    @router.post(
        "/api/v1/chat",
        response_model=ChatResponseDTO,
        summary="Wysyła wiadomość do Agenta i zwraca pełną odpowiedź w jednym żądaniu",
        tags=["Chat & Sessions"],
    )
    async def chat_interact(req: SendChatMessageRequest) -> ChatResponseDTO:
        await _require_registered(req.sender_id)
        if agent_engine.is_session_busy(req.session_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sesja '{req.session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.",
            )
        try:
            return await agent_engine.interact(
                session_id=req.session_id,
                prompt=req.message,
                sender_id=req.sender_id,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Błąd generowania odpowiedzi przez Agenta: {err}",
            ) from err

    @router.post(
        "/api/v1/chat/stream",
        summary="Wysyła wiadomość do Agenta i strumieniuje odpowiedź w czasie rzeczywistym via SSE",
        tags=["Chat & Sessions"],
    )
    async def chat_interact_stream(req: SendChatMessageRequest):
        await _require_registered(req.sender_id)
        if agent_engine.is_session_busy(req.session_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sesja '{req.session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.",
            )

        async def event_generator():
            try:
                async for event in agent_engine.interact_stream(
                    session_id=req.session_id,
                    prompt=req.message,
                    sender_id=req.sender_id,
                ):
                    yield f"data: {json.dumps({**event.payload, 'type': event.type})}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as err:
                error_payload = json.dumps({"type": "error", "error": str(err)})
                yield f"data: {error_payload}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @router.post(
        "/api/v1/chat/send",
        status_code=status.HTTP_202_ACCEPTED,
        summary="Odpala ture Agenta w tle i od razu wraca (\"wyslij i zapomnij\") - renderowanie na zywo wylacznie przez GET .../watch",
        tags=["Chat & Sessions"],
    )
    async def chat_send(req: SendChatMessageRequest):
        """Mirror `AgentEngine.start_interaction()` (dotad uzywanego tylko przez satelity
        glosowe) wystawiony przez REST — Web UI korzysta z niego zamiast blokujacego
        `/api/v1/chat` albo samo-strumieniujacego `/api/v1/chat/stream`, zeby wyslanie
        wiadomosci nie roznilo sie architektonicznie od tury zainicjowanej przez satelite:
        jedynym zrodlem renderowania (dla kazdego inicjatora) jest kanal obserwujacy
        `GET /api/v1/chat/sessions/{session_id}/watch`."""
        await _require_registered(req.sender_id)
        try:
            agent_engine.start_interaction(
                session_id=req.session_id, prompt=req.message, sender_id=req.sender_id
            )
        except RuntimeError as err:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err
        return {"success": True, "session_id": req.session_id}

    @router.post(
        "/api/v1/chat/cancel",
        summary="Anuluje aktywne generowanie odpowiedzi dla podanej sesji (Web, Satelita, Cron)",
        tags=["Chat & Sessions"],
    )
    async def cancel_chat_interact(req: CancelChatApiRequest):
        cancelled = await agent_engine.cancel_interaction(req.session_id)
        return {"success": cancelled, "session_id": req.session_id}

    return router

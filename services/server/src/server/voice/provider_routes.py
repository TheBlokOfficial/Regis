"""Router REST CRUD dla dostawców STT/TTS (`ai.stt`/`ai.tts`).

Cała logika (lista, aktywacja, tworzenie, edycja, usuwanie, maskowanie sekretów)
mieszka w `ai/provider_crud.py`, wspólnie z dostawcami LLM — tutaj zostaje sam
transport: ścieżki, kody odpowiedzi i opakowanie surowych pól w DTO właściwe dla
domeny. Wcześniej bloki STT i TTS w tym pliku różniły się dosłownie trzema
literami w nazwach, a oba były kopią `network/routes/providers.py`.

Montowany osobno od `voice/routes.py` (status/klienci), pod tym samym prefiksem
`/api/v1/voice`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from shared import DeletionResponse, ProviderMetadataResponse

from server.ai.provider_crud import ProviderCrud, ProviderNotFoundError, UnsupportedProviderTypeError
from server.ai.stt import STTFactory, STTProviderType, STTRegistry
from server.ai.tts import TTSFactory, TTSProviderType, TTSRegistry
from server.voice.dto import (
    CreateSTTProviderRequest,
    CreateTTSProviderRequest,
    SelectSTTProviderRequest,
    SelectTTSProviderRequest,
    STTProviderDTO,
    STTProviderListResponse,
    TTSProviderDTO,
    TTSProviderListResponse,
    UpdateProviderRequest,
)


def _not_found(err: ProviderNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


def create_voice_providers_router(stt_registry: STTRegistry, tts_registry: TTSRegistry) -> APIRouter:
    """Tworzy router dla CRUD dostawców STT/TTS."""
    router = APIRouter()

    stt = ProviderCrud(stt_registry, STTFactory.get_all_schemas, STTProviderType, "STT")
    tts = ProviderCrud(tts_registry, TTSFactory.get_all_schemas, TTSProviderType, "TTS")

    # -- STT ------------------------------------------------------------------

    @router.get("/stt/providers/schemas", response_model=ProviderMetadataResponse, tags=["STT Providers"])
    async def get_stt_provider_schemas() -> ProviderMetadataResponse:
        return STTFactory.get_all_schemas()

    @router.get("/stt/providers", response_model=STTProviderListResponse, tags=["STT Providers"])
    async def get_stt_providers() -> STTProviderListResponse:
        payloads, active_id = await stt.list_payloads()
        return STTProviderListResponse(providers=[STTProviderDTO(**p) for p in payloads], active_id=active_id)

    @router.put("/stt/providers/active", response_model=STTProviderListResponse, tags=["STT Providers"])
    async def set_active_stt_provider(req: SelectSTTProviderRequest) -> STTProviderListResponse:
        try:
            await stt.activate(req.provider_id)
        except ProviderNotFoundError as err:
            raise _not_found(err) from err
        return await get_stt_providers()

    @router.post(
        "/stt/providers", response_model=STTProviderDTO, status_code=status.HTTP_201_CREATED, tags=["STT Providers"]
    )
    async def create_stt_provider(req: CreateSTTProviderRequest) -> STTProviderDTO:
        try:
            return STTProviderDTO(**await stt.create(req.type, req.name, req.options, req.custom_id))
        except (UnsupportedProviderTypeError, ValueError) as err:
            raise _bad_request(err) from err

    @router.put("/stt/providers/{provider_id}", response_model=STTProviderDTO, tags=["STT Providers"])
    async def update_stt_provider(provider_id: str, req: UpdateProviderRequest) -> STTProviderDTO:
        try:
            return STTProviderDTO(**await stt.update(provider_id, req.name, req.options))
        except ProviderNotFoundError as err:
            raise _not_found(err) from err

    @router.delete(
        "/stt/providers/{provider_id}", response_model=DeletionResponse, tags=["STT Providers"]
    )
    async def delete_stt_provider(provider_id: str) -> DeletionResponse:
        try:
            await stt.delete(provider_id)
        except ProviderNotFoundError as err:
            raise _not_found(err) from err
        except ValueError as err:
            raise _bad_request(err) from err
        return DeletionResponse(deleted_id=provider_id)

    # -- TTS ------------------------------------------------------------------

    @router.get("/tts/providers/schemas", response_model=ProviderMetadataResponse, tags=["TTS Providers"])
    async def get_tts_provider_schemas() -> ProviderMetadataResponse:
        return TTSFactory.get_all_schemas()

    @router.get("/tts/providers", response_model=TTSProviderListResponse, tags=["TTS Providers"])
    async def get_tts_providers() -> TTSProviderListResponse:
        payloads, active_id = await tts.list_payloads()
        return TTSProviderListResponse(providers=[TTSProviderDTO(**p) for p in payloads], active_id=active_id)

    @router.put("/tts/providers/active", response_model=TTSProviderListResponse, tags=["TTS Providers"])
    async def set_active_tts_provider(req: SelectTTSProviderRequest) -> TTSProviderListResponse:
        try:
            await tts.activate(req.provider_id)
        except ProviderNotFoundError as err:
            raise _not_found(err) from err
        return await get_tts_providers()

    @router.post(
        "/tts/providers", response_model=TTSProviderDTO, status_code=status.HTTP_201_CREATED, tags=["TTS Providers"]
    )
    async def create_tts_provider(req: CreateTTSProviderRequest) -> TTSProviderDTO:
        try:
            return TTSProviderDTO(**await tts.create(req.type, req.name, req.options, req.custom_id))
        except (UnsupportedProviderTypeError, ValueError) as err:
            raise _bad_request(err) from err

    @router.put("/tts/providers/{provider_id}", response_model=TTSProviderDTO, tags=["TTS Providers"])
    async def update_tts_provider(provider_id: str, req: UpdateProviderRequest) -> TTSProviderDTO:
        try:
            return TTSProviderDTO(**await tts.update(provider_id, req.name, req.options))
        except ProviderNotFoundError as err:
            raise _not_found(err) from err

    @router.delete(
        "/tts/providers/{provider_id}", response_model=DeletionResponse, tags=["TTS Providers"]
    )
    async def delete_tts_provider(provider_id: str) -> DeletionResponse:
        try:
            await tts.delete(provider_id)
        except ProviderNotFoundError as err:
            raise _not_found(err) from err
        except ValueError as err:
            raise _bad_request(err) from err
        return DeletionResponse(deleted_id=provider_id)

    return router

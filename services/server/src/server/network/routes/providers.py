"""Router REST CRUD dla dostawców LLM.

Logika wspólna z STT/TTS (lista, aktywacja, tworzenie, edycja, usuwanie,
maskowanie sekretów) mieszka w `ai/provider_crud.py` — tutaj zostaje sam
transport plus jedyny endpoint specyficzny dla LLM: odkrywanie modeli.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from shared import (
    CreateLLMProviderRequest,
    LLMProviderDTO,
    LLMProviderListResponse,
    ProviderMetadataResponse,
    ProviderModelsResponse,
    SelectLLMProviderRequest,
    UpdateLLMProviderRequest,
)

from server.ai.llm import BackendRegistry, LLMFactory, ProviderType
from server.ai.llm.model_catalog import discover_models, fallback_options_schema
from server.ai.provider_crud import ProviderCrud, ProviderNotFoundError, UnsupportedProviderTypeError


def create_providers_router(
    backend_registry: BackendRegistry,
) -> APIRouter:
    """Tworzy router dla punktów końcowych konfiguracji dostawców LLM."""
    router = APIRouter()
    crud = ProviderCrud(backend_registry, LLMFactory.get_all_schemas, ProviderType, "LLM")

    @router.get(
        "/api/v1/llm/providers/schemas",
        response_model=ProviderMetadataResponse,
        summary="Pobiera generyczne specyfikacje pól opcji dla dostępnych typów dostawców LLM",
        tags=["LLM Providers"],
    )
    async def get_llm_provider_schemas() -> ProviderMetadataResponse:
        return LLMFactory.get_all_schemas()

    @router.get(
        "/api/v1/llm/providers",
        response_model=LLMProviderListResponse,
        summary="Pobiera listę skonfigurowanych dostawców LLM oraz ID aktywnego",
        tags=["LLM Providers"],
    )
    async def get_llm_providers() -> LLMProviderListResponse:
        payloads, active_id = await crud.list_payloads()
        return LLMProviderListResponse(providers=[LLMProviderDTO(**p) for p in payloads], active_id=active_id)

    @router.put(
        "/api/v1/llm/providers/active",
        response_model=LLMProviderListResponse,
        summary="Wybiera i przełącza aktywnego dostawcę LLM w agencie",
        tags=["LLM Providers"],
    )
    async def set_active_llm_provider(req: SelectLLMProviderRequest) -> LLMProviderListResponse:
        try:
            await crud.activate(req.provider_id)
        except ProviderNotFoundError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
        return await get_llm_providers()

    @router.post(
        "/api/v1/llm/providers",
        response_model=LLMProviderDTO,
        status_code=status.HTTP_201_CREATED,
        summary="Tworzy nową instancję dostawcy LLM i zapisuje plik JSON",
        tags=["LLM Providers"],
    )
    async def create_llm_provider(req: CreateLLMProviderRequest) -> LLMProviderDTO:
        try:
            return LLMProviderDTO(**await crud.create(req.type, req.name, req.options, req.custom_id))
        except (UnsupportedProviderTypeError, ValueError) as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

    @router.delete(
        "/api/v1/llm/providers/{provider_id}",
        summary="Usuwa plik instancji dostawcy LLM z dysku",
        tags=["LLM Providers"],
    )
    async def delete_llm_provider(provider_id: str) -> dict[str, Any]:
        try:
            await crud.delete(provider_id)
        except ProviderNotFoundError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
        return {"success": True, "deleted_id": provider_id}

    @router.put(
        "/api/v1/llm/providers/{provider_id}",
        response_model=LLMProviderDTO,
        summary="Edytuje istniejący preset LLM (nazwa + opcje; typ jest niezmienny)",
        tags=["LLM Providers"],
    )
    async def update_llm_provider(provider_id: str, req: UpdateLLMProviderRequest) -> LLMProviderDTO:
        try:
            return LLMProviderDTO(**await crud.update(provider_id, req.name, req.options))
        except ProviderNotFoundError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

    @router.get(
        "/api/v1/llm/providers/{provider_id}/models",
        response_model=ProviderModelsResponse,
        summary="Lista modeli dostępnych dla tego presetu wraz z formularzem parametrów każdego z nich",
        tags=["LLM Providers"],
    )
    async def get_llm_provider_models(provider_id: str) -> ProviderModelsResponse:
        """Odkrywanie idzie przez SERWER, nie z przeglądarki: zapytanie o listę modeli
        wymaga klucza API presetu, a ten nigdy nie opuszcza serwera w jawnej postaci."""
        config = (await backend_registry.load_all_instances()).get(provider_id)
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dostawca LLM o ID '{provider_id}' nie istnieje.",
            )

        models, detail = await discover_models(config)
        return ProviderModelsResponse(
            models=models,
            detail=detail,
            fallback_options_schema=fallback_options_schema(config.type),
        )

    return router

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


def _secret_field_names(provider_type: str) -> set[str]:
    """Pola oznaczone w schemacie dostawcy jako `password` — jedno źródło prawdy zarówno
    dla maskowania w odpowiedzi, jak i dla zachowywania wartości przy edycji."""
    return {
        spec.name
        for type_spec in LLMFactory.get_all_schemas().provider_types
        if type_spec.type == provider_type
        for spec in type_spec.options_schema
        if spec.type == "password"
    }


def _merge_preserving_secrets(
    provider_type: str, existing: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Pole sekretne puste/pominięte w żądaniu **zachowuje** obecną wartość.

    Frontend nigdy nie zna prawdziwego klucza API (GET zwraca go zamaskowanego kropkami),
    więc nie może go odesłać z powrotem — bez tego każdy zapis formularza edycji
    nadpisywałby klucz ciągiem kropek. Ten sam wzorzec co token Home Assistant
    (`world/routes.py`).
    """
    merged = dict(incoming)
    for field_name in _secret_field_names(provider_type):
        if not str(merged.get(field_name, "")).strip():
            if field_name in existing:
                merged[field_name] = existing[field_name]
            else:
                merged.pop(field_name, None)
    return merged


def _mask_secret_options(provider_type: str, options: dict[str, Any]) -> dict[str, Any]:
    """Maskuje wartości pól oznaczonych w schemacie dostawcy jako 'password' (np. api_key).

    Klucze API nie powinny nigdy opuszczać serwera w czystym tekście przez API REST —
    pola sekretne są rozpoznawane na podstawie tego samego schematu, którego używa
    frontend do renderowania formularzy (LLMFactory.get_all_schemas(), Single Source of Truth).
    """
    secret_fields = _secret_field_names(provider_type)
    if not secret_fields:
        return options

    masked = dict(options)
    for field_name in secret_fields:
        value = masked.get(field_name)
        if isinstance(value, str) and value:
            visible = value[-4:] if len(value) > 4 else ""
            masked[field_name] = f"{'•' * (len(value) - len(visible))}{visible}"
    return masked


def create_providers_router(
    backend_registry: BackendRegistry,
) -> APIRouter:
    """Tworzy router dla punktów końcowych konfiguracji dostawców LLM."""
    router = APIRouter()

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
        instances = await backend_registry.load_all_instances()
        active_id = await backend_registry.get_active_backend_id()

        providers_dto = []
        for cfg in instances.values():
            type_str = cfg.type.value if hasattr(cfg.type, "value") else str(cfg.type)
            providers_dto.append(
                LLMProviderDTO(
                    id=cfg.id,
                    type=type_str,
                    name=cfg.name,
                    options=_mask_secret_options(type_str, cfg.options),
                    is_active=(cfg.id == active_id),
                )
            )

        return LLMProviderListResponse(providers=providers_dto, active_id=active_id)

    @router.put(
        "/api/v1/llm/providers/active",
        response_model=LLMProviderListResponse,
        summary="Wybiera i przełącza aktywnego dostawcę LLM w agencie",
        tags=["LLM Providers"],
    )
    async def set_active_llm_provider(req: SelectLLMProviderRequest) -> LLMProviderListResponse:
        all_instances = await backend_registry.load_all_instances()
        if req.provider_id not in all_instances:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dostawca LLM o ID '{req.provider_id}' nie istnieje.",
            )

        await backend_registry.set_active_backend_id(req.provider_id)

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
            p_type = ProviderType(req.type.upper())
        except ValueError:
            supported = ", ".join(t.value for t in ProviderType)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Niewspierany typ dostawcy LLM: '{req.type}'. Dozwolone: {supported}.",
            ) from None

        try:
            created_cfg = await backend_registry.create_instance(
                provider_type=p_type,
                name=req.name,
                options=req.options,
                custom_id=req.custom_id,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

        active_id = await backend_registry.get_active_backend_id()
        type_str = created_cfg.type.value if hasattr(created_cfg.type, "value") else str(created_cfg.type)

        return LLMProviderDTO(
            id=created_cfg.id,
            type=type_str,
            name=created_cfg.name,
            options=_mask_secret_options(type_str, created_cfg.options),
            is_active=(created_cfg.id == active_id),
        )

    @router.delete(
        "/api/v1/llm/providers/{provider_id}",
        summary="Usuwa plik instancji dostawcy LLM z dysku",
        tags=["LLM Providers"],
    )
    async def delete_llm_provider(provider_id: str):
        try:
            deleted = await backend_registry.delete_instance(provider_id)
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dostawca LLM o ID '{provider_id}' nie istnieje.",
                )
            return {"success": True, "deleted_id": provider_id}
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            ) from err

    @router.put(
        "/api/v1/llm/providers/{provider_id}",
        response_model=LLMProviderDTO,
        summary="Edytuje istniejący preset LLM (nazwa + opcje; typ jest niezmienny)",
        tags=["LLM Providers"],
    )
    async def update_llm_provider(provider_id: str, req: UpdateLLMProviderRequest) -> LLMProviderDTO:
        instances = await backend_registry.load_all_instances()
        existing = instances.get(provider_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dostawca LLM o ID '{provider_id}' nie istnieje.",
            )

        type_str = existing.type.value if hasattr(existing.type, "value") else str(existing.type)
        merged = _merge_preserving_secrets(type_str, existing.options, req.options)
        try:
            updated = await backend_registry.update_instance(provider_id, req.name, merged)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err

        active_id = await backend_registry.get_active_backend_id()
        return LLMProviderDTO(
            id=updated.id,
            type=type_str,
            name=updated.name,
            options=_mask_secret_options(type_str, updated.options),
            is_active=(updated.id == active_id),
        )

    @router.get(
        "/api/v1/llm/providers/{provider_id}/models",
        response_model=ProviderModelsResponse,
        summary="Lista modeli dostępnych dla tego presetu wraz z formularzem parametrów każdego z nich",
        tags=["LLM Providers"],
    )
    async def get_llm_provider_models(provider_id: str) -> ProviderModelsResponse:
        """Odkrywanie idzie przez SERWER, nie z przeglądarki: zapytanie o listę modeli
        wymaga klucza API presetu, a ten nigdy nie opuszcza serwera w jawnej postaci."""
        instances = await backend_registry.load_all_instances()
        config = instances.get(provider_id)
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

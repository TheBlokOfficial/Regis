from fastapi import APIRouter, HTTPException
from typing import List
import os

from controller.config import loader as config
from controller.config.schemas import CloudProviderConfig, CloudProvidersConfig

router_cloud = APIRouter(prefix="/api/cloud-providers", tags=["cloud-providers"])

def get_cloud_providers() -> list[CloudProviderConfig]:
    """Zwraca listę dostawców, ewentualnie migrując klucz z .env jeśli plik jest pusty."""
    cfg = config.load(CloudProvidersConfig)
    
    if not cfg.root:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")
        if api_key:
            provider = CloudProviderConfig(
                id="auto_openrouter",
                type="openrouter",
                api_key=api_key,
                model=model,
                priority=50
            )
            cfg.root.append(provider)
            config.save(cfg)
    return cfg.root

def _save_cloud_providers(providers: list[CloudProviderConfig]) -> None:
    config.save(CloudProvidersConfig(providers))


@router_cloud.get("", response_model=List[CloudProviderConfig])
def get_providers():
    providers = get_cloud_providers()
    masked = []
    for p in providers:
        p_copy = p.model_dump()
        if p_copy.get("api_key"):
            prefix = p_copy["api_key"][:3]
            p_copy["api_key"] = f"{prefix}...****"
        masked.append(CloudProviderConfig(**p_copy))
    return masked

@router_cloud.post("", response_model=CloudProviderConfig)
def add_provider(provider: CloudProviderConfig):
    providers = get_cloud_providers()
    if any(p.id == provider.id for p in providers):
        raise HTTPException(status_code=400, detail=f"Provider z id '{provider.id}' już istnieje.")
    
    providers.append(provider)
    _save_cloud_providers(providers)
    return provider

@router_cloud.patch("/{provider_id}", response_model=CloudProviderConfig)
def update_provider(provider_id: str, updates: dict):
    providers = get_cloud_providers()
    
    for idx, p in enumerate(providers):
        if p.id == provider_id:
            p_dict = p.model_dump()
            
            if "api_key" in updates and "..." in updates["api_key"]:
                del updates["api_key"]
                
            p_dict.update(updates)
            
            try:
                validated = CloudProviderConfig(**p_dict)
            except Exception as e:
                raise HTTPException(status_code=422, detail=str(e))
                
            providers[idx] = validated
            _save_cloud_providers(providers)
            return validated
            
    raise HTTPException(status_code=404, detail="Provider nie znaleziony")

@router_cloud.delete("/{provider_id}")
def delete_provider(provider_id: str):
    providers = get_cloud_providers()
    new_providers = [p for p in providers if p.id != provider_id]
    
    if len(new_providers) == len(providers):
        raise HTTPException(status_code=404, detail="Provider nie znaleziony")
        
    _save_cloud_providers(new_providers)
    return {"status": "ok"}

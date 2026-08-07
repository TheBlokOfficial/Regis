import logging
from fastapi import APIRouter, HTTPException
from typing import List, Literal
from pydantic import BaseModel

from controller.llm.providers import get_cloud_providers, save_cloud_providers

class CloudProviderConfig(BaseModel):
    """Konfiguracja providera chmurowego (np. OpenRouter, Groq)."""
    id: str
    type: str  # np. "openrouter"
    api_key: str
    model: str
    mode: Literal["basic", "extended"] = "extended"
    priority: int = 50

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cloud-providers", tags=["cloud-providers"])

@router.get("", response_model=List[CloudProviderConfig])
def get_providers():
    providers = get_cloud_providers()
    # Mask api keys before returning to UI
    masked = []
    for p in providers:
        p_copy = dict(p)
        if "api_key" in p_copy and p_copy["api_key"]:
            prefix = p_copy["api_key"][:3]
            p_copy["api_key"] = f"{prefix}...****"
        masked.append(CloudProviderConfig(**p_copy))
    return masked

@router.post("", response_model=CloudProviderConfig)
def add_provider(provider: CloudProviderConfig):
    providers = get_cloud_providers()
    # Create a new copy of the list to avoid mutating cache directly before saving
    new_providers = list(providers)
    
    if any(p.get("id") == provider.id for p in new_providers):
        raise HTTPException(status_code=400, detail=f"Provider z id '{provider.id}' już istnieje.")
    
    new_providers.append(provider.model_dump())
    
    success = save_cloud_providers(new_providers)
    if not success:
         raise HTTPException(status_code=500, detail="Błąd zapisu konfiguracji dostawców chmurowych")
    
    return provider

@router.patch("/{provider_id}", response_model=CloudProviderConfig)
def update_provider(provider_id: str, updates: dict):
    providers = get_cloud_providers()
    new_providers = list(providers)
    
    for idx, p in enumerate(new_providers):
        if p.get("id") == provider_id:
            # Create a copy of the dictionary to avoid mutating cache directly
            p_copy = dict(p)
            
            # Aktualizacja pól (ignoruj zamaskowany klucz API z UI)
            if "api_key" in updates and "..." in updates["api_key"]:
                del updates["api_key"]
                
            p_copy.update(updates)
            
            try:
                validated = CloudProviderConfig(**p_copy)
            except Exception as e:
                raise HTTPException(status_code=422, detail=str(e))
                
            new_providers[idx] = validated.model_dump()
            success = save_cloud_providers(new_providers)
            
            if not success:
                raise HTTPException(status_code=500, detail="Błąd zapisu konfiguracji dostawców chmurowych")
                
            return validated
            
    raise HTTPException(status_code=404, detail="Provider nie znaleziony")

@router.delete("/{provider_id}")
def delete_provider(provider_id: str):
    providers = get_cloud_providers()
    new_providers = [p for p in providers if p.get("id") != provider_id]
    
    if len(new_providers) == len(providers):
        raise HTTPException(status_code=404, detail="Provider nie znaleziony")
        
    success = save_cloud_providers(new_providers)
    if not success:
         raise HTTPException(status_code=500, detail="Błąd zapisu konfiguracji dostawców chmurowych")
    
    return {"status": "ok"}

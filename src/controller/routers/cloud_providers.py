import json
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from typing import List

from core import config
from core.schemas import CloudProviderConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cloud-providers", tags=["cloud-providers"])

PROVIDERS_FILE = Path(config.DATA_DIR) / "cloud_providers.json"

def _load_providers() -> list[dict]:
    if not PROVIDERS_FILE.exists():
        return []
    try:
        data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Błąd ładowania pliku cloud_providers.json: {e}")
        return []

def _save_providers(providers: list[dict]):
    try:
        PROVIDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROVIDERS_FILE.write_text(json.dumps(providers, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Błąd zapisu pliku cloud_providers.json: {e}")
        raise HTTPException(status_code=500, detail="Błąd zapisu konfiguracji dostawców chmurowych")

@router.get("", response_model=List[CloudProviderConfig])
def get_providers():
    providers = _load_providers()
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
    providers = _load_providers()
    if any(p.get("id") == provider.id for p in providers):
        raise HTTPException(status_code=400, detail=f"Provider z id '{provider.id}' już istnieje.")
    
    providers.append(provider.model_dump())
    _save_providers(providers)
    
    # Przeładowanie globalnego rejestru
    from controller.providers import reload_cloud_providers
    reload_cloud_providers()
    
    return provider

@router.patch("/{provider_id}", response_model=CloudProviderConfig)
def update_provider(provider_id: str, updates: dict):
    providers = _load_providers()
    for idx, p in enumerate(providers):
        if p.get("id") == provider_id:
            # Aktualizacja pól (ignoruj zamaskowany klucz API z UI)
            if "api_key" in updates and "..." in updates["api_key"]:
                del updates["api_key"]
                
            p.update(updates)
            
            try:
                validated = CloudProviderConfig(**p)
            except Exception as e:
                raise HTTPException(status_code=422, detail=str(e))
                
            providers[idx] = validated.model_dump()
            _save_providers(providers)
            
            # Przeładowanie
            from controller.providers import reload_cloud_providers
            reload_cloud_providers()
            
            return validated
            
    raise HTTPException(status_code=404, detail="Provider nie znaleziony")

@router.delete("/{provider_id}")
def delete_provider(provider_id: str):
    providers = _load_providers()
    new_providers = [p for p in providers if p.get("id") != provider_id]
    
    if len(new_providers) == len(providers):
        raise HTTPException(status_code=404, detail="Provider nie znaleziony")
        
    _save_providers(new_providers)
    
    from controller.providers import reload_cloud_providers
    reload_cloud_providers()
    
    return {"status": "ok"}

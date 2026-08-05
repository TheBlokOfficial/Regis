import logging
import httpx
from client.utils import LLMConnectionError


def get_available_models(ollama_url: str) -> list[str]:
    import requests
    tags_url = f"{ollama_url}/api/tags"
    try:
        response = requests.get(tags_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return [model['name'] for model in data.get('models', [])]
    except Exception:
        return []


async def is_available(ollama_url: str) -> bool:
    tags_url = f"{ollama_url}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(tags_url)
            return response.status_code == 200
    except httpx.RequestError:
        return False


async def ensure_model_exists(client: httpx.AsyncClient, ollama_url: str, model_name: str) -> bool:
    """Sprawdza czy model jest obecny, jeśli nie, próbuje go pobrać."""
    try:
        tags_resp = await client.get(f"{ollama_url}/api/tags")
        tags_resp.raise_for_status()
        models = [m.get("name") for m in tags_resp.json().get("models", [])]
        
        if not any(model_name in m or m in model_name for m in models):
            logging.info(f"[Ollama Pull] Rozpoczynam pobieranie brakującego modelu '{model_name}'...")
            pull_resp = await client.post(
                f"{ollama_url}/api/pull", 
                json={"name": model_name}, 
                timeout=600.0
            )
            pull_resp.raise_for_status()
            logging.info(f"[Ollama Pull] Model '{model_name}' pobrany pomyślnie.")
        return True
    except Exception as e:
        logging.error(f"[Ollama] Błąd weryfikacji/pobierania modelu: {e}")
        return False


async def preload_model(ollama_url: str, model_name: str) -> bool:
    """Wstępnie ładuje model do pamięci VRAM."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            success = await ensure_model_exists(client, ollama_url, model_name)
            if not success:
                return False
            
            url = f"{ollama_url}/api/generate"
            payload = {"model": model_name, "keep_alive": -1}
            
            response = await client.post(url, json=payload)
            response.raise_for_status()
        logging.info(f"Wstępnie załadowano model {model_name} do VRAM.")
        return True
    except Exception as e:
        logging.error(f"Nie udało się połączyć z Ollamą lub załadować modelu: {e}")
        return False


async def unload_model(ollama_url: str, model_name: str) -> None:
    """Wyładowuje model z pamięci VRAM."""
    url = f"{ollama_url}/api/generate"
    payload = {"model": model_name, "keep_alive": 0}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
        logging.info(f"Wysłano żądanie wyładowania modelu {model_name} z VRAM.")
    except Exception as e:
        logging.warning(f"Nie udało się wyładować modelu: {e}")

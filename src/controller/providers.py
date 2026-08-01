import logging
from core.llm_backends.base import LLMBackend
from controller.openrouter_backend import OpenRouterBackend
from core.llm_backends.ollama import OllamaBackend
import controller.registry as registry

def get_llm_backend() -> LLMBackend | None:
    """Zwraca najlepszy dostępny backend LLM lub None, jeśli żaden nie działa.
    Priorytet:
    1. Lokalny Worker (tier = 'regis' - mocny komputer)
    2. OpenRouter (chmura)
    3. Lokalny Worker (tier = 'butler' - malinka / awaryjny)
    """
    # 1. Szukamy mocnego workera (regis)
    for worker in registry.worker_registry.values():
        if worker.get("tier") == "regis":
            return OllamaBackend(model_name="worker")
            
    # 2. Próbujemy chmurę (OpenRouter)
    try:
        openrouter = OpenRouterBackend()
        if openrouter.is_available():
            return openrouter
    except Exception as e:
        logging.warning(f"Błąd sprawdzania OpenRouterBackend: {e}")

    # 3. Fallback na dowolnego workera (butler / awaryjny)
    if registry.worker_registry:
        return OllamaBackend(model_name="worker")
        
    return None

def has_llm_provider() -> bool:
    return get_llm_backend() is not None

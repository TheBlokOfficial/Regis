import logging
from core.llm_backends.base import LLMBackend
from controller.openrouter_backend import OpenRouterBackend
from core.llm_backends.ollama import OllamaBackend
import controller.registry as registry

def get_llm_backend() -> LLMBackend | None:
    """Zwraca najlepszy dostępny backend LLM według priorytetu (wyższa cyfra = wyższy priorytet).
    Przykładowe priorytety:
      100: Lokalny Worker GPU (np. mocny PC / Minisforum)
       50: OpenRouter (chmura)
       10: Awaryjny Worker (np. RPi5)
    """
    from core import config
    settings = config.load_settings()

    candidates: list[tuple[int, LLMBackend]] = []

    # 1. Zarejestrowane Węzły Robocze (Workery)
    for worker in registry.worker_registry.values():
        prio = worker.get("priority", 10)
        candidates.append((prio, OllamaBackend(model_name="worker")))

    # 2. Provider chmurowy OpenRouter
    try:
        openrouter = OpenRouterBackend()
        if openrouter.is_available():
            openrouter_prio = settings.get("openrouter_priority", 50)
            candidates.append((openrouter_prio, openrouter))
    except Exception as e:
        logging.warning(f"Błąd sprawdzania OpenRouterBackend: {e}")

    if not candidates:
        return None

    # Sortowanie malejąco według priority (100 wyżej niż 50, 50 wyżej niż 10)
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected_prio, selected_backend = candidates[0]
    logging.debug(f"Wybrano LLM Backend: {selected_backend.get_provider_name()} z priorytetem {selected_prio}")
    return selected_backend

def has_llm_provider() -> bool:
    return get_llm_backend() is not None

"""
Resolver / Fabryka Dostawców LLM (Warstwa 2 – Providers).

Jedno miejsce wyliczające i zwracające najlepszy dostępny backend LLM
(usługi aplikacji klienckich lub konfiguracje chmurowe) według priorytetów.
"""
import logging

import controller.core.client_registry as client_registry
import controller.endpoints.cloud as endpoints_cloud
from controller.providers.llm.base import LLMBackend
from controller.providers.llm.openrouter import OpenRouterBackend
from controller.providers.llm.client_app import ClientAppBackend

logger = logging.getLogger(__name__)


def get_llm_backend() -> LLMBackend | None:
    """Zwraca najlepszy dostępny backend LLM według priorytetu."""
    candidates: list[tuple[int, LLMBackend, dict]] = []

    # 1. Zarejestrowane usługi aplikacji klienckich (np. Regis Desktop)
    for worker in client_registry.client_registry.values():
        prio = worker.get("priority", 10)
        model_name = worker.get("model_name", "qwen3.5:9b")
        client_id = worker.get("id", "")
        if client_id:
            candidates.append((prio, ClientAppBackend(client_id=client_id, model_name=model_name), worker))

    # 2. Dostawcy chmurowi zarejestrowani w cloud_store
    for cp in endpoints_cloud.get_cloud_providers():
        if cp.get("type") == "openrouter" and cp.get("api_key") and cp.get("model"):
            try:
                backend = OpenRouterBackend(
                    api_key=cp["api_key"],
                    model_name=cp["model"]
                )
                if backend.is_available():
                    candidates.append((cp.get("priority", 50), backend, cp))
            except Exception as e:
                logger.warning(f"Błąd ładowania chmury {cp.get('id')}: {e}")

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected_prio, selected_backend, meta = candidates[0]

    logger.debug(f"Wybrano LLM Backend: {selected_backend.get_provider_name()} z priorytetem {selected_prio}")
    return selected_backend


def has_llm_provider() -> bool:
    """Zwraca True, jeśli dostępny jest jakikolwiek aktywny backend LLM."""
    return get_llm_backend() is not None

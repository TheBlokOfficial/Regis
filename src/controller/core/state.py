"""
Centralny rejestr globalnych zmiennych stanu systemu Kontrolera.

Inicjalizowany podczas fazy startowej (lifespan w app.py).
Odczytywany przez wiele modułów — stanowi jedyne źródło prawdy
dla globalnego stanu runtime (nie konfiguracji).
"""
import time

# Czas startu procesu Kontrolera — używany do obliczania uptime
controller_start_time: float = time.time()

# Aktywne integracje zewnętrzne: {integration_id: BaseIntegration}
# Np. {"home_assistant": HomeAssistantIntegration(...)}
integration_registry: dict = {}

# Cache głównych ustawień systemowych (kopia SystemSettings.model_dump())
# Używany przez moduły które potrzebują ustawień bez wczytywania pliku
_settings_cache: dict = {}

# Skrót do klienta HTTP Home Assistant (z integration_registry["home_assistant"].ha_client)
# Ustawiany przy ładowaniu integracji HA
ha_client = None  # HomeAssistantClient | None

def register_integration(integration) -> None:
    """Rejestruje integrację zewnętrzną w Kontrolerze."""
    import logging
    global ha_client
    integration_registry[integration.id] = integration
    if integration.id == "home_assistant":
        ha_client = getattr(integration, "ha_client", None)
    logging.info(f"Zarejestrowano integrację: {integration.name} ({integration.id})")

# Rejestr narzędzi Agenta LLM — inicjalizowany w lifespan
tools_registry = None  # ToolsRegistry | None

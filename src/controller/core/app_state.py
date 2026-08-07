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
# Ustawiany przez client_store.register_integration() przy ładowaniu integracji HA
ha_client = None  # HomeAssistantClient | None

# Rejestr narzędzi Agenta LLM — inicjalizowany w lifespan
tools_registry = None  # ToolsRegistry | None

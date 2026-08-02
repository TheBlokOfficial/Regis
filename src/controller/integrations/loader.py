"""
Ładowarka integracji zewnętrznych w Kontrolerze Regis.

Odpowiada za automatyczne wykrywanie i inicjalizowanie aktywnych integracji
na podstawie konfiguracji systemowej, chroniąc app.py przed bezpośrednimi
zależnościami od konkretnych klas integracji (MANIFEST.md §3.5).
"""
from typing import Any
from controller.integrations.base import BaseIntegration


def load_integrations(
    settings: dict[str, Any],
    aliases: dict[str, str] = None,
    virtual_groups: dict[str, list[str]] = None,
) -> list[BaseIntegration]:
    """Ładuje i zwraca listę aktywowanych integracji w systemie."""
    integrations: list[BaseIntegration] = []

    # Integracja Home Assistant (aktywna, jeśli skonfigurowano ha_url lub ha_token)
    if settings.get("ha_url") or settings.get("ha_token"):
        from controller.integrations.ha_integration import HomeAssistantIntegration
        integrations.append(
            HomeAssistantIntegration.from_settings(
                settings=settings,
                aliases=aliases,
                virtual_groups=virtual_groups,
            )
        )

    return integrations

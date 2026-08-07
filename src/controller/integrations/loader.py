"""
Ładowarka integracji zewnętrznych w Kontrolerze Regis.

Odpowiada za automatyczne wykrywanie i inicjalizowanie aktywnych integracji
na podstawie konfiguracji systemowej, chroniąc app.py przed bezpośrednimi
zależnościami od konkretnych klas integracji (MANIFEST.md §3.5).
"""
from typing import Any
from controller.integrations.base import BaseIntegration


def load_integrations(
    settings: dict[str, Any] | Any = None,
    aliases: dict[str, str] = None,
    virtual_groups: dict[str, list[str]] = None,
) -> list[BaseIntegration]:
    """Ładuje i zwraca listę aktywowanych integracji w systemie."""
    if settings is None:
        from controller.config import loader as config, SystemSettings
        settings = config.load(SystemSettings)

    settings_dict = settings.model_dump() if hasattr(settings, "model_dump") else settings

    if aliases is None or virtual_groups is None:
        from controller.config import load, AliasesConfig, VirtualGroupsConfig
        if aliases is None:
            aliases = load(AliasesConfig).root
        if virtual_groups is None:
            virtual_groups = load(VirtualGroupsConfig).root

    integrations: list[BaseIntegration] = []

    # Integracja Home Assistant (aktywna, jeśli skonfigurowano ha_url lub ha_token)
    if settings_dict.get("ha_url") or settings_dict.get("ha_token"):
        from controller.integrations.ha_integration import HomeAssistantIntegration
        integrations.append(
            HomeAssistantIntegration.from_settings(
                settings=settings_dict,
                aliases=aliases,
                virtual_groups=virtual_groups,
            )
        )

    return integrations

"""Addon Smart Home — dostarcza agentowi generyczne narzędzia sterowania urządzeniami."""

from server.addons.smart_home.addon import SmartHomeAddon
from server.addons.smart_home.base import DeviceIntegration
from server.addons.smart_home.devices import Device, DeviceGroup, DeviceRegistry
from server.addons.smart_home.models import (
    DeviceGroupFileContent,
    DeviceGroupInstanceConfig,
    IntegrationFileContent,
    IntegrationInstanceConfig,
)

__all__ = [
    "Device",
    "DeviceGroup",
    "DeviceGroupFileContent",
    "DeviceGroupInstanceConfig",
    "DeviceIntegration",
    "DeviceRegistry",
    "IntegrationFileContent",
    "IntegrationInstanceConfig",
    "SmartHomeAddon",
]

"""Plugin Smart Home — dostarcza agentowi generyczne narzędzia sterowania urządzeniami."""

from server.plugins.smart_home.contract import DeviceIntegration
from server.plugins.smart_home.models import (
    Device,
    DeviceGroup,
    DeviceGroupFileContent,
    DeviceGroupInstanceConfig,
    IntegrationFileContent,
    IntegrationInstanceConfig,
)
from server.plugins.smart_home.plugin import SmartHomePlugin
from server.plugins.smart_home.registry import DeviceRegistry

__all__ = [
    "Device",
    "DeviceGroup",
    "DeviceGroupFileContent",
    "DeviceGroupInstanceConfig",
    "DeviceIntegration",
    "DeviceRegistry",
    "IntegrationFileContent",
    "IntegrationInstanceConfig",
    "SmartHomePlugin",
]

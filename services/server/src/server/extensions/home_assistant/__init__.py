"""Rozszerzenie Home Assistant — dostarcza agentowi generyczne narzędzia sterowania urządzeniami."""

from server.extensions.home_assistant.extension import HomeAssistantExtension
from server.extensions.home_assistant.models import Device, DeviceGroup

__all__ = ["Device", "DeviceGroup", "HomeAssistantExtension"]

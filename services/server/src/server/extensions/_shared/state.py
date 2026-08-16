"""Wspólny model pliku `state.json` — jeden przełącznik enabled na rozszerzenie.

Nie jest to kontrakt międzywarstwowy, tylko uniknięcie duplikacji tego samego
trzy-liniowego modelu Pydantic w każdym rozszerzeniu implementującym
`NetworkExtension` (`server.network.extension_contract`).
"""

from pydantic import BaseModel, Field


class ExtensionStateFileContent(BaseModel):
    """Zawartość pliku `data/extensions/{extension_id}/state.json`."""

    enabled: bool = Field(default=True, description="Czy rozszerzenie aktywnie dostarcza wkład agentowi")

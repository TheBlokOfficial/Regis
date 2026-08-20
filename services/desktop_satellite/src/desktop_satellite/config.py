"""Trwała, lokalna tożsamość satelity — `sender_id` generowany raz (UUID4) przy
pierwszym uruchomieniu i zapisywany na dysku, żeby kolejne starty nie wymagały
ręcznego podawania flagi. Ten sam wzorzec (`ConfigStore`+`get_service_root`)
co `server/config.py`.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from shared import ConfigStore, get_service_root


class SatelliteSettings(BaseModel):
    """Lokalna konfiguracja satelity."""

    sender_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Trwały opaque sender_id")


SERVICE_DIR = get_service_root(__file__)
CONFIG_PATH = SERVICE_DIR / "config" / "settings.json"

config_store = ConfigStore(SatelliteSettings, CONFIG_PATH)


def load_or_create_sender_id() -> str:
    """Wczytuje `sender_id` z `config/settings.json`, tworząc plik z nowym UUID4
    przy pierwszym uruchomieniu (brak pliku)."""
    return config_store.load().sender_id

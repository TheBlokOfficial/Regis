import logging
from pathlib import Path

import controller.core.state as app_state
from controller.config import loader as config

logger = logging.getLogger(__name__)


def _read_prompt_file() -> str:
    """Ładuje treść pliku promptu systemu Regis."""
    path = Path(config.DATA_DIR) / "prompts" / "system_prompt.md"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning(f"Błąd ładowania promptu {path}: {e}")
    return "Jesteś Regisem, rzeczowym asystentem domowym."


def build_system_prompt(room: str | None = None) -> str:
    """Buduje i składa system prompt dla tożsamości Regis."""
    menu = app_state.tools_registry.get_global_menu() if app_state.tools_registry else ""
    room_info = f"OBECNY POKÓJ: {room}" if room else ""

    sys_prompt = _read_prompt_file()
    sections = [sys_prompt, menu, room_info]

    return "\n\n".join(section for section in sections if section)

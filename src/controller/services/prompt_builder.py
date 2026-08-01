import logging
from pathlib import Path

import controller.registry as registry
from core import config
from core.schemas import render_tools_for_prompt

logger = logging.getLogger(__name__)


def _read_prompt_file() -> str:
    """Ładuje treść pliku promptu systemu Regis."""
    path = Path(config.CONFIG_DIR) / "prompts" / "system_prompt.md"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning(f"Błąd ładowania promptu {path}: {e}")
    return "Jesteś Regisem, rzeczowym asystentem domowym."


def build_system_prompt(room: str | None = None, native_tools: bool = False) -> str:
    """Buduje i składa system prompt dla tożsamości Regis."""
    # 1. Klocki budulcowe
    sys_prompt = _read_prompt_file()
    menu = registry.tools_registry.get_global_menu() if registry.tools_registry else ""
    room_info = f"OBECNY POKÓJ: {room}" if room else ""

    # 2. Układ sekcji
    if native_tools:
        sections = [sys_prompt, menu, room_info]
    else:
        tools_text = render_tools_for_prompt()
        sections = [tools_text, menu, room_info, sys_prompt]

    # 3. Połączenie niepustych sekcji
    return "\n\n".join(section for section in sections if section)

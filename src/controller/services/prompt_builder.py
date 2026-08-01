import logging
from pathlib import Path

import controller.registry as registry
from core import config
from core.schemas import render_tools_for_prompt

logger = logging.getLogger(__name__)


def _read_prompt_file(tier: str) -> str:
    """Ładuje treść pliku promptu dla podanego tieru lub zwraca domyślny fallback."""
    path = Path(config.CONFIG_DIR) / "prompts" / f"tier_{tier}.md"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning(f"Błąd ładowania promptu {path}: {e}")
    return "Jesteś asystentem domowym."


def build_system_prompt(tier: str, room: str | None = None, native_tools: bool = False) -> str:
    """Buduje i składa system prompt dla wybranego tieru."""
    # 1. Klocki budulcowe
    tier_prompt = _read_prompt_file(tier)
    menu = registry.tools_registry.get_global_menu() if registry.tools_registry else ""
    room_info = f"OBECNY POKÓJ: {room}" if room else ""

    # 2. Układ sekcji w zależności od trybu
    if tier == "butler" or native_tools:
        sections = [tier_prompt, menu, room_info]
    else:
        tools_text = render_tools_for_prompt(tier)
        sections = [tools_text, menu, room_info, tier_prompt]

    # 3. Połączenie niepustych sekcji
    return "\n\n".join(section for section in sections if section)

import logging
from pathlib import Path

import controller.registry as registry
from controller import config

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


def build_system_prompt(room: str | None = None, mode: str = "extended") -> str:
    """Buduje i składa system prompt dla tożsamości Regis."""
    menu = registry.tools_registry.get_global_menu() if registry.tools_registry else ""
    room_info = f"OBECNY POKÓJ: {room}" if room else ""
    
    if mode == "basic":
        # W trybie basic model działa jak bezstanowy parser - minimalizujemy prompt
        sys_prompt = "Jesteś asystentem domowym Regis. Masz wykonać polecenie użytkownika korzystając wyłącznie z udostępnionego menu urządzeń. Bądź zwięzły."
        sections = [sys_prompt, menu, room_info]
    else:
        # 1. Klocki budulcowe
        sys_prompt = _read_prompt_file()
        # W trybie extended (chmura lub zaawansowany węzeł) przesyłamy pełny prompt.
        sections = [sys_prompt, menu, room_info]

    # 3. Połączenie niepustych sekcji
    return "\n\n".join(section for section in sections if section)

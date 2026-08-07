"""
Główny Punkt Wejścia (Entry Point) i Zarządca Cyklu Życia Kontrolera Regis.
"""
import sys
import os
import signal
import logging
import uvicorn

from controller.logger import setup_logging
from controller.app import DEFAULT_CONTROLLER_PORT


def setup_signal_handlers() -> None:
    """Podłącza sygnały wyjścia z systemu operacyjnego do czystego zamknięcia."""
    def handle_exit(signum, frame):
        logging.info(f"Otrzymano sygnał wyłączenia ({signum}). Zamykanie Kontrolera...")
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)
    except ValueError:
        pass


def main() -> None:
    """Główny zarządca cyklu życia i pętli Kontrolera Regis."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    # 1. Inicjalizacja zunifikowanego systemu logowania
    setup_logging("controller")
    logging.info("Główny proces Kontrolera Regis uruchomiony.")

    # 2. Obsługa sygnałów wyjścia
    setup_signal_handlers()

    # 3. Konfiguracja i uruchomienie serwera ASGI Uvicorn
    logging.info(f"Uruchamianie serwera Uvicorn na porcie {DEFAULT_CONTROLLER_PORT}...")
    config_obj = uvicorn.Config(
        app="controller.app:app",
        host="0.0.0.0",
        port=DEFAULT_CONTROLLER_PORT,
        log_config=None,
    )
    server = uvicorn.Server(config_obj)
    server.run()


if __name__ == "__main__":
    main()
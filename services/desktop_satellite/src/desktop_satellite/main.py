"""Punkt wejścia satelity desktopowej.

Cienki: parsuje argumenty, ustawia logowanie i oddaje wątek główny zasobnikowi
(`tray.py`), podczas gdy pętla połączenia pracuje w wątku roboczym (`app.py`).
Ten podział jest wymuszony przez `pystray`, które na Windows musi mieszkać w wątku
głównym — dawne `asyncio.run(run_forever(...))` zajmowało dokładnie ten wątek.

Dwa tryby:

* **domyślny (zasobnik)** — postać produkcyjna: bez okna konsoli, sterowanie z menu
  ikony, logi do pliku w katalogu użytkownika;
* **`--console`** — dawne zachowanie, do pracy nad kodem: bez zasobnika, logi na
  standardowe wyjście, zatrzymanie Ctrl+C. Wybierany automatycznie, gdy `pystray`
  nie jest zainstalowany, żeby uruchomienie ze źródeł nie wymagało grupy `build`.
"""

from __future__ import annotations

import argparse
import threading

from shared import get_logger, setup_logging, user_state_dir

from desktop_satellite.app import SatelliteApp
from desktop_satellite.config import CONFIG_PATH, load_or_create_sender_id

logger = get_logger("regis.desktop_satellite.main")

APP_NAME = "Regis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Satelita desktopowa Regis (Windows/Linux).")
    parser.add_argument(
        "--server-url",
        default=None,
        help="WS bazowy adres serwera (np. ws://192.168.1.10:8000/ws/voice). Pominięcie włącza auto-discovery UDP.",
    )
    parser.add_argument(
        "--sender-id",
        default=None,
        help="Opaque sender_id tej satelity. Pominięcie użyje/utworzy trwały UUID w pliku konfiguracji.",
    )
    parser.add_argument("--log-level", default="INFO", help="Poziom logowania (domyślnie INFO).")
    parser.add_argument(
        "--console",
        action="store_true",
        help="Tryb konsolowy: bez ikony w zasobniku, logi na wyjście, zatrzymanie Ctrl+C.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Plik logu ZAWSZE, nie tylko w trybie bezokienkowym: gdy nie ma konsoli, jest
    # jedynym śladem po awarii, a gdy jest — nie przeszkadza.
    setup_logging(args.log_level, log_file=user_state_dir(APP_NAME) / "logs" / "satellite.log")

    if args.sender_id:
        sender_id = args.sender_id
        logger.info(f"sender_id: '{sender_id}' (z flagi --sender-id).")
    else:
        sender_id = load_or_create_sender_id()
        logger.info(f"sender_id: '{sender_id}' (z {CONFIG_PATH}).")

    if args.console or not _tray_available():
        _run_console(sender_id, args.server_url)
    else:
        _run_tray(sender_id, args.server_url)


def _tray_available() -> bool:
    """Czy da się w ogóle pokazać ikonę. Brak `pystray`/`Pillow` (uruchomienie ze
    źródeł bez grupy `build`) degraduje do trybu konsolowego zamiast wywracać start."""
    try:
        import PIL  # noqa: F401
        import pystray  # noqa: F401
    except ImportError:
        logger.info("Brak pystray/Pillow — uruchamiam w trybie konsolowym.")
        return False
    return True


def _run_tray(sender_id: str, server_url: str | None) -> None:
    from desktop_satellite.tray import TrayController

    app = SatelliteApp(sender_id=sender_id, server_url_override=server_url)
    tray = TrayController(app, config_path=str(CONFIG_PATH))
    app.set_status_listener(tray.on_status_change)
    try:
        tray.run()
    finally:
        app.stop()


def _run_console(sender_id: str, server_url: str | None) -> None:
    app = SatelliteApp(sender_id=sender_id, server_url_override=server_url)
    app.start()
    try:
        # Wątek roboczy jest `daemon`, więc bez tego czekania proces zakończyłby się
        # natychmiast po `start()`. `Event().wait()` (a nie pętla ze `sleep`) budzi się
        # na Ctrl+C od razu, bez czekania na koniec interwału.
        threading.Event().wait()
    except KeyboardInterrupt:
        logger.info("Zatrzymano (Ctrl+C).")
    finally:
        app.stop()


if __name__ == "__main__":
    main()

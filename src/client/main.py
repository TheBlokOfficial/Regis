import argparse
import atexit
import os
import signal
import sys
import threading
import pystray

from client import controller_client
from client.logger import setup_logging
from client.process_manager import cleanup_orphaned_processes, stop_all_services
from client.tray import create_default_icon, get_menu

app_tray: pystray.Icon | None = None


def quit_all(icon=None) -> None:
    """Zatrzymuje wszystkie procesy potomne, wyrejestrowuje klienta i zamyka aplikację w zasobniku."""
    stop_all_services()
    controller_client.unregister()
    if app_tray:
        app_tray.stop()
    elif icon:
        icon.stop()
    os._exit(0)


def hide_console_window() -> None:
    """Ukrywa okno konsoli w systemie Windows (SW_HIDE)."""
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd != 0:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass


def setup_signal_handlers() -> None:
    """Podłącza sygnały wyjścia z systemu operacyjnego do funkcji wyjścia."""
    atexit.register(quit_all)
    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: quit_all())
        signal.signal(signal.SIGINT, lambda signum, frame: quit_all())
    except ValueError:
        pass  # Ignoruj jeśli nie jesteśmy w głównym wątku


def main() -> None:
    """Główny punkt wejścia (Entry Point) aplikacji klienckiej Regis."""
    global app_tray

    parser = argparse.ArgumentParser(description="Regis Client Application")
    parser.add_argument("--console", action="store_true", help="Pokaż okno konsoli i wyjście logów (tryb debugowania)")
    args = parser.parse_args()

    # 1. Konfiguracja logowania
    setup_logging("client", console_output=args.console)

    # 2. Ukrycie konsoli na Windowsie (jeśli brak flagi --console)
    if not args.console:
        hide_console_window()

    # 3. Inicjalizacja środowiska i sygnałów wyjścia
    cleanup_orphaned_processes()
    setup_signal_handlers()

    # 4. Rejestracja Klienta i start komunikacji WebSocket w tle
    controller_client.register()
    ws_thread = threading.Thread(target=controller_client.start_ws_client, daemon=True)
    ws_thread.start()

    # 5. Uruchomienie interfejsu w zasobniku systemowym (pętla główna)
    app_tray = pystray.Icon("regis_client", create_default_icon(), "Regis Client", menu=get_menu(quit_all))
    app_tray.run()


if __name__ == "__main__":
    main()

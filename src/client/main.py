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

tray_icon: pystray.Icon | None = None


def quit_all(icon=None, item=None) -> None:
    """Zatrzymuje wszystkie procesy potomne, wyrejestrowuje klienta i zamyka ikonę zasobnika."""
    stop_all_services()
    controller_client.unregister()
    if tray_icon:
        tray_icon.stop()
    elif icon:
        icon.stop()
    os._exit(0)


def main() -> None:
    """Główny punkt wejścia (Entry Point) aplikacji klienckiej Regis."""
    global tray_icon

    parser = argparse.ArgumentParser(description="Regis Client Application")
    parser.add_argument("--console", action="store_true", help="Pokaż okno konsoli i wyjście logów (tryb debugowania)")
    args = parser.parse_args()

    # 1. Konfiguracja logowania (zawsze do pliku, do konsoli tylko gdy podano --console)
    setup_logging("client", console_output=args.console)

    # 2. Jeśli jesteśmy na Windowsie i brak flagi --console, ukryj okno wiersza poleceń
    if sys.platform == "win32" and not args.console:
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd != 0:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass

    # 3. Bezwzględne czyszczenie starych podprocesów-sierot
    cleanup_orphaned_processes()

    # 4. Rejestracja globalnych sygnałów wyjścia
    atexit.register(quit_all)
    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: quit_all())
        signal.signal(signal.SIGINT, lambda signum, frame: quit_all())
    except ValueError:
        pass  # Ignoruj jeśli nie jesteśmy w głównym wątku

    # 5. Rejestracja Klienta w Kontrolerze
    controller_client.register()

    # 6. Uruchomienie klienta WebSocket w osobnym wątku (komunikacja w czasie rzeczywistym)
    ws_thread = threading.Thread(target=controller_client.start_ws_client, daemon=True)
    ws_thread.start()

    # 7. Uruchomienie ikony w zasobniku systemowym (pętla interfejsu użytkownika)
    tray_icon = pystray.Icon("regis_client", create_default_icon(), "Regis Client", menu=get_menu(quit_all))
    tray_icon.run()


if __name__ == "__main__":
    main()

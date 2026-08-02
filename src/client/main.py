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


def set_console_visibility(visible: bool) -> None:
    """Kontroluje widoczność okna konsoli w systemie Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                SW_HIDE = 0
                SW_SHOW = 5
                ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW if visible else SW_HIDE)
        except Exception:
            pass


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
    """Główny punkt wejścia (Entry Point) aplikacji klienckiej Regis.

    Zarządza cyklem życia aplikacji (sygnały OS, okno konsoli, ikona w zasobniku, połączenie z Kontrolerem).
    """
    global tray_icon

    parser = argparse.ArgumentParser(description="Aplikacja Kliencka Regis")
    parser.add_argument("--debug", action="store_true", help="Uruchamia pełny tryb debugowania (wyświetla konsolę z logami DEBUG)")
    parser.add_argument("--gui", action="store_true", help="Pokaż okno konsoli z logami w czasie rzeczywistym")
    parser.add_argument("--headless", action="store_true", help="Uruchom w trybie bezgłowym (bez ikony w zasobniku systemowym)")
    parser.add_argument("--no-console", action="store_true", help="Ukryj okno konsoli i wyłącz wyjście na konsolę")
    args = parser.parse_args()

    # Logika widoczności konsoli: domyślnie pokazuje okno jeśli podano --debug lub --gui, ukrywa jeśli podano --no-console
    show_console = (args.debug or args.gui) and not args.no_console
    set_console_visibility(show_console)

    setup_logging(service_name="client", debug=args.debug, enable_console=show_console)

    # 1. Czyszczenie starych podprocesów-sierot
    cleanup_orphaned_processes()

    # 2. Rejestracja globalnych sygnałów wyjścia OS
    atexit.register(quit_all)
    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: quit_all())
        signal.signal(signal.SIGINT, lambda signum, frame: quit_all())
    except ValueError:
        pass  # Ignoruj jeśli nie jesteśmy w głównym wątku

    # 3. Rejestracja Klienta w Kontrolerze
    controller_client.register()

    # 4. Uruchomienie klienta WebSocket w osobnym wątku (komunikacja w czasie rzeczywistym)
    ws_thread = threading.Thread(target=controller_client.start_ws_client, daemon=True)
    ws_thread.start()

    # 5. Uruchomienie pętli interfejsu (Zasobnik systemowy lub utrzymanie wątku w trybie headless)
    if not args.headless:
        tray_icon = pystray.Icon("regis_client", create_default_icon(), "Regis Client", menu=get_menu(quit_all))
        tray_icon.run()
    else:
        try:
            ws_thread.join()
        except KeyboardInterrupt:
            quit_all()


if __name__ == "__main__":
    main()

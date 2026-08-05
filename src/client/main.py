import atexit
import os
import signal
import socket
import sys
import threading
import pystray

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from client import controller_api
from client.logger import setup_logging
from client.process_manager import cleanup_orphaned_processes, stop_all_services
from client.tray import create_default_icon, get_menu

app_tray: pystray.Icon | None = None
_instance_socket: socket.socket | None = None


def ensure_single_instance(port: int = 47829) -> None:
    """Sprawdza czy kolejna instancja Regis Client nie jest już uruchomiona w systemie.

    Korzysta z zamka gniazda na pętli zwrotnej (127.0.0.1). Jeśli port jest zajęty,
    aplikacja wypisuje komunikat i natychmiast się wyłącza.
    """
    global _instance_socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", port))
        s.listen(1)
        _instance_socket = s
    except OSError:
        print("[Single Instance] Aplikacja Regis Client jest już uruchomiona w tle.")
        sys.exit(0)


def quit_all(icon=None) -> None:
    """Zatrzymuje wszystkie procesy potomne, wyrejestrowuje klienta i zamyka aplikację w zasobniku."""
    stop_all_services()
    controller_api.unregister()
    if app_tray:
        app_tray.stop()
    elif icon:
        icon.stop()
    os._exit(0)


_win_ctrl_handler = None

def setup_signal_handlers() -> None:
    """Podłącza sygnały wyjścia z systemu operacyjnego do funkcji wyjścia."""
    global _win_ctrl_handler
    atexit.register(quit_all)
    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: quit_all())
        signal.signal(signal.SIGINT, lambda signum, frame: quit_all())
    except ValueError:
        pass  # Ignoruj jeśli nie jesteśmy w głównym wątku

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            PHANDLER_ROUTINE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
            
            def _win_handler(ctrl_type):
                quit_all()
                return True

            _win_ctrl_handler = PHANDLER_ROUTINE(_win_handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_win_ctrl_handler, True)
        except Exception:
            pass


def main() -> None:
    """Główny punkt wejścia (Entry Point) aplikacji klienckiej Regis."""
    global app_tray

    # 0. Zabezpieczenie przed podwójnym uruchomieniem
    ensure_single_instance()

    # 1. Inicjalizacja lokalna aplikacji
    setup_logging("client")
    cleanup_orphaned_processes()
    setup_signal_handlers()

    from client.internal_proxy import start_internal_proxy_thread
    start_internal_proxy_thread()

    # 2. Uruchomienie stałego połączenia WebSocket dla zdarzeń czasu rzeczywistego i auto-rejestracji
    ws_thread = threading.Thread(target=controller_api.start_ws_client, daemon=True)
    ws_thread.start()
    controller_api.wait_for_ws_connection(timeout=3.0)

    # 5. Uruchomienie zasobnika systemowego (pętla główna)
    app_tray = pystray.Icon("regis_client", create_default_icon(), "Regis", menu=get_menu(quit_all))
    app_tray.run()


if __name__ == "__main__":
    main()

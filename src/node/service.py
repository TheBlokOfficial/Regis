import atexit
import os
import signal
import threading
import pystray

from node.config import load_settings, save_settings
from node.controller_client import (
    register,
    unregister,
    start_ws_client
)
from node.process_manager import (cleanup_orphaned_processes, stop_all_services)
from node.tray import create_default_icon, get_menu

# Dla kompatybilności ze starymi odwołaniami:
get_settings = load_settings
save_settings = save_settings

tray_icon: pystray.Icon | None = None


def quit_all(icon=None, item=None) -> None:
    """Zatrzymuje wszystkie procesy potomne, wyrejestrowuje węzeł i zamyka ikonę zasobnika."""
    stop_all_services()
    unregister()
    if tray_icon:
        tray_icon.stop()
    elif icon:
        icon.stop()
    os._exit(0)


def run_service() -> None:
    """Główna funkcja uruchamiająca usługę Węzła w tle (Pystray Tray + Subservices)."""
    global tray_icon

    # 1. Bezwzględne czyszczenie starych podprocesów-sierot
    cleanup_orphaned_processes()

    # 2. Rejestracja globalnych sygnałów wyjścia
    atexit.register(quit_all)
    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: quit_all())
        signal.signal(signal.SIGINT, lambda signum, frame: quit_all())
    except ValueError:
        pass  # Ignoruj jeśli nie jesteśmy w głównym wątku

    # 3. Rejestracja Węzła w Kontrolerze (przekazanie identyfikatora node_id)
    register()

    # 5. Uruchomienie ikony w zasobniku oraz klienta WebSocket
    tray_icon = pystray.Icon("node", create_default_icon(), "Regis Node", menu=get_menu(quit_all))
    
    ws_thread = threading.Thread(target=start_ws_client, daemon=True)
    ws_thread.start()

    tray_icon.run()


if __name__ == "__main__":
    run_service()

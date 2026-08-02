import webbrowser
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
from client.config import load_settings


def create_default_icon() -> Image.Image:
    """Tworzy prostą kwadratową ikonę 64x64 dla zasobnika systemowego."""
    image = Image.new('RGB', (64, 64), color=(40, 40, 40))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(0, 120, 215))
    return image


def open_dashboard() -> None:
    """Otwiera panel kontrolny w przeglądarce internetowej."""
    settings = load_settings()
    server_url = settings.get("server_url", settings.get("controller_url", "http://127.0.0.1:8000"))
    if server_url == "auto":
        try:
            from protocol.discovery import discover_controller
            server_url = discover_controller()
        except Exception:
            server_url = "http://127.0.0.1:8000"
    webbrowser.open(server_url)


def get_menu(on_quit_callback) -> pystray.Menu:
    """Zwraca menu kontekstowe paska zadań."""
    settings = load_settings()
    name = settings.get("instance_name", "Regis Node")
    return pystray.Menu(
        item(lambda text: f"Regis Node — {name}", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("Otwórz panel kontrolny", lambda: open_dashboard()),
        pystray.Menu.SEPARATOR,
        item("Zamknij", on_quit_callback),
    )

"""Ikona w zasobniku systemowym — jedyny interfejs satelity w trybie bezokienkowym.

Menu nie jest ozdobą, tylko **zastępuje kanał, który znika razem z konsolą**. README
kazał dotąd odczytać `sender_id` z logu startowego, żeby zarejestrować satelitę w Web UI
(zakładka Świat → Nadawcy). Po przejściu na `--noconsole` tego logu nikt nie zobaczy,
więc `sender_id` musi dać się skopiować stąd — inaczej świeżo zainstalowanej satelity
nie da się w ogóle dodać do systemu.

Stąd zestaw pozycji: tożsamość (kopiuj `sender_id`), stan połączenia, wymuszenie
ponownego połączenia, przełącznik autostartu, dostęp do logów i wyjście.

`pystray` na Windows wymaga wątku głównego — `run()` go zajmuje i wraca dopiero przy
zamknięciu. Pętla `asyncio` mieszka w `SatelliteApp` (osobny wątek, patrz `app.py`).
"""

from __future__ import annotations

import sys
from typing import Any

from shared import get_logger

from desktop_satellite import autostart
from desktop_satellite.app import AppStatus, LinkState, SatelliteApp

logger = get_logger("regis.desktop_satellite.tray")

ICON_SIZE = 64


class TrayController:
    """Ikona i menu; całą pracę deleguje do `SatelliteApp` i `autostart`."""

    def __init__(self, app: SatelliteApp, config_path: str) -> None:
        self._app = app
        self._config_path = config_path
        self._icon: Any = None

    # --------------------------------------------------------------------------
    # Cykl życia
    # --------------------------------------------------------------------------

    def run(self) -> None:
        """Zajmuje wątek główny do czasu wyjścia z aplikacji."""
        import pystray

        self._icon = pystray.Icon(
            "regis-satellite",
            icon=self._render_icon(connected=False),
            title="Regis — satelita",
            menu=pystray.Menu(*self._menu_items()),
        )
        self._app.start()
        self._icon.run()

    def on_status_change(self, status: AppStatus) -> None:
        """Wołane z wątku roboczego `SatelliteApp`.

        `update_menu()` i podmiana `icon` są w `pystray` bezpieczne między wątkami —
        to jedyny powód, dla którego nie potrzebujemy tu własnej kolejki."""
        icon = self._icon
        if icon is None:
            return
        icon.icon = self._render_icon(connected=status.state is LinkState.CONNECTED)
        icon.title = f"Regis — {status.label}"
        icon.update_menu()

    # --------------------------------------------------------------------------
    # Menu
    # --------------------------------------------------------------------------

    def _menu_items(self) -> list[Any]:
        import pystray

        items: list[Any] = [
            pystray.MenuItem(lambda _: self._app.status.label, None, enabled=False),
            pystray.MenuItem(lambda _: f"sender_id: {self._app.sender_id}", self._copy_sender_id),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Połącz ponownie", self._reconnect),
        ]
        if autostart.is_supported():
            items.append(
                pystray.MenuItem(
                    "Uruchamiaj przy starcie systemu",
                    self._toggle_autostart,
                    checked=lambda _: autostart.is_enabled(),
                )
            )
        items += [
            pystray.MenuItem("Otwórz katalog logów", self._open_logs),
            pystray.MenuItem("Otwórz konfigurację", self._open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Zakończ", self._quit),
        ]
        return items

    def _copy_sender_id(self) -> None:
        """Kopiuje `sender_id` do schowka — pierwszy krok rejestracji klienta w Web UI.

        Bez zależności od `tkinter`/`pyperclip`: na Windows wystarczy `clip`, na Linux
        `wl-copy`/`xclip`. Gdy żadne nie zadziała, `sender_id` i tak jest widoczny
        w samym menu i w logu — kopiowanie to wygoda, nie jedyna droga."""
        text = self._app.sender_id
        try:
            if sys.platform == "win32":
                import subprocess

                subprocess.run("clip", input=text.encode("utf-16-le"), check=True, shell=True)
                return
            import shutil
            import subprocess

            for tool, args in (("wl-copy", ["wl-copy"]), ("xclip", ["xclip", "-selection", "clipboard"])):
                if shutil.which(tool):
                    subprocess.run(args, input=text.encode(), check=True)
                    return
            logger.warning("Brak narzędzia do schowka (wl-copy/xclip) — sender_id widoczny w menu.")
        except Exception as err:
            logger.warning(f"Nie udało się skopiować sender_id do schowka: {err}")

    def _reconnect(self) -> None:
        self._app.reconnect()

    def _toggle_autostart(self) -> None:
        autostart.toggle()

    def _open_logs(self) -> None:
        autostart.open_directory(autostart.logs_dir())

    def _open_config(self) -> None:
        from pathlib import Path

        autostart.open_directory(Path(self._config_path).parent)

    def _quit(self) -> None:
        logger.info("Zamykanie satelity z menu zasobnika.")
        self._app.stop()
        if self._icon is not None:
            self._icon.stop()

    # --------------------------------------------------------------------------
    # Ikona
    # --------------------------------------------------------------------------

    @staticmethod
    def _render_icon(connected: bool) -> Any:
        """Prosty znacznik rysowany w locie zamiast pliku `.png` w zasobach.

        Zasób graficzny trzeba by dołączyć do bundla PyInstallera i utrzymywać
        w repozytorium; dwa kolorowe kółka niosą tu dokładnie tę samą informację,
        co ikona: czy satelita jest połączona."""
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        fill = (46, 204, 113, 255) if connected else (127, 140, 141, 255)
        draw.ellipse((4, 4, ICON_SIZE - 4, ICON_SIZE - 4), fill=fill)
        draw.ellipse((20, 20, ICON_SIZE - 20, ICON_SIZE - 20), fill=(24, 24, 24, 255))
        return image

"""Cykl życia satelity oderwany od wątku głównego.

**Dlaczego to nie może zostać w `main.py`.** `pystray` na Windows wymaga wątku
głównego procesu — pętla komunikatów ikony w zasobniku musi tam mieszkać. Dotychczasowe
`asyncio.run(run_forever(...))` zajmowało dokładnie ten wątek, więc dołożenie zasobnika
nie było zmianą kosmetyczną, tylko przebudową punktu wejścia: `asyncio` schodzi tutaj,
do wątku roboczego, a wątek główny oddajemy ikonie.

Klasa ma jedną dodatkową odpowiedzialność ponad to, co robiła dawna pętla: **wystawia
stan na zewnątrz**. Bez konsoli nie ma jak zobaczyć, czy satelita jest połączona, więc
`on_state_change` niesie tę informację do menu zasobnika. Callback wołany jest z wątku
roboczego — wywołujący odpowiada za bezpieczne przeniesienie go do swojego świata
(dla `pystray` wystarcza `icon.update_menu()`, które jest thread-safe).
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from shared import get_logger

from desktop_satellite.audio import FRAME_DURATION_MS, MicCapture, SpeakerPlayback
from desktop_satellite.discovery import discover_server
from desktop_satellite.protocol_client import ProtocolClient
from desktop_satellite.session import SatelliteSession
from desktop_satellite.vad import SilenceVadDetector

logger = get_logger("regis.desktop_satellite.app")

RECONNECT_DELAY_SECONDS = 3.0
DISCOVERY_TIMEOUT_SECONDS = 15.0


class LinkState(Enum):
    """Co pokazać w zasobniku. Celowo grubsze niż `SessionState` — użytkownik chce
    wiedzieć „czy to w ogóle działa", a nie w której fazie tury jesteśmy."""

    SEARCHING = auto()
    """Szukam serwera przez auto-discovery albo czekam na ponowną próbę."""

    CONNECTED = auto()
    """Połączona i nasłuchuje."""

    STOPPED = auto()


@dataclass(frozen=True)
class AppStatus:
    """Migawka stanu dla zasobnika — niezmienna, więc bezpieczna do przekazania
    między wątkami bez żadnej synchronizacji."""

    state: LinkState
    sender_id: str
    server_url: str | None = None
    detail: str = ""

    @property
    def label(self) -> str:
        if self.state is LinkState.CONNECTED:
            return f"Połączona: {self.server_url}"
        if self.state is LinkState.STOPPED:
            return "Zatrzymana"
        return self.detail or "Szukam serwera..."


StatusListener = Callable[[AppStatus], None]


class SatelliteApp:
    """Pętla połączenia satelity, uruchamiana w osobnym wątku.

    `start()` wraca natychmiast, `stop()` domyka pętlę i czeka na wątek. Obie metody
    są bezpieczne do wołania z wątku głównego (czyli z menu zasobnika)."""

    def __init__(
        self,
        sender_id: str,
        server_url_override: str | None = None,
        on_status_change: StatusListener | None = None,
    ) -> None:
        self.sender_id = sender_id
        self._server_url_override = server_url_override
        self._on_status_change = on_status_change
        self._status = AppStatus(state=LinkState.SEARCHING, sender_id=sender_id)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._task: asyncio.Task[None] | None = None
        self._reconnect_now: asyncio.Event | None = None
        # Pętla powstaje dopiero w wątku roboczym, więc `start()` wraca, ZANIM da się
        # ją o cokolwiek poprosić. Bez tej bramki „Zakończ" kliknięte zaraz po starcie
        # trafiało w `self._loop is None` i po cichu nie robiło nic — aplikacja
        # zostawała uruchomiona, a ikona znikała.
        self._ready = threading.Event()

    # --------------------------------------------------------------------------
    # Sterowanie z wątku głównego
    # --------------------------------------------------------------------------

    @property
    def status(self) -> AppStatus:
        return self._status

    def set_status_listener(self, listener: StatusListener | None) -> None:
        """Podpina obserwatora po utworzeniu obu stron.

        Zasobnik potrzebuje referencji do aplikacji, a aplikacja do obserwatora, więc
        konstruktor jednego nie może dostać gotowego drugiego. Metoda zamiast zapisu
        wprost do pola — wiązanie jest częścią publicznego kontraktu tej klasy."""
        self._on_status_change = listener

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_loop, name="regis-satellite", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Zatrzymuje pętlę i czeka na zamknięcie wątku.

        `call_soon_threadsafe` to jedyny bezpieczny sposób dotknięcia pętli `asyncio`
        z innego wątku — bezpośrednie `task.cancel()` byłoby wyścigiem. Czekanie na
        `_ready` obsługuje przypadek graniczny „zatrzymaj natychmiast po starcie",
        w którym pętli jeszcze fizycznie nie ma."""
        thread = self._thread
        if thread is None:
            return
        if self._ready.wait(timeout=timeout) and self._loop is not None:
            self._loop.call_soon_threadsafe(self._cancel_task)
        else:
            logger.warning("Pętla satelity nie zdążyła wystartować — zamykam bez anulowania.")
        thread.join(timeout=timeout)
        self._thread = None
        self._loop = None
        self._ready.clear()
        self._set_status(LinkState.STOPPED)

    def reconnect(self) -> None:
        """Przerywa czekanie na kolejną próbę połączenia — pozycja „Połącz ponownie"
        w menu. Bez tego użytkownik po naprawieniu sieci czeka do końca backoffu.

        Kliknięcie, zanim pętla wstanie, jest bezgłośnie ignorowane: ona i tak właśnie
        podejmuje pierwszą próbę."""
        loop, event = self._loop, self._reconnect_now
        if loop is None or event is None:
            return
        loop.call_soon_threadsafe(event.set)

    # --------------------------------------------------------------------------
    # Wątek roboczy
    # --------------------------------------------------------------------------

    def _cancel_task(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def _run_loop(self) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._reconnect_now = asyncio.Event()
        self._task = asyncio.current_task()
        self._ready.set()
        try:
            await self._run_forever()
        except asyncio.CancelledError:
            logger.info("Zatrzymano pętlę satelity.")

    async def _run_forever(self) -> None:
        mic = MicCapture()
        speaker = SpeakerPlayback()
        while True:
            server_url = self._server_url_override or await self._discover()
            if server_url is None:
                await self._wait_before_retry("Serwer nie znaleziony (auto-discovery).")
                continue

            link = ProtocolClient(server_url, self.sender_id)
            try:
                logger.info(f"Łączenie z serwerem [{server_url}, sender_id: '{self.sender_id}'] ...")
                await link.connect()
                mic.start()
                self._set_status(LinkState.CONNECTED, server_url=server_url)
                session = SatelliteSession(link=link, speaker=speaker, vad_factory=self._build_vad)
                await session.run(mic)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # połączenie padło/serwer nieosiągalny — reconnect
                logger.warning(f"Połączenie przerwane: {err}.")
            finally:
                mic.stop()
                await link.close()
            await self._wait_before_retry("Połączenie zamknięte.")

    async def _discover(self) -> str | None:
        self._set_status(LinkState.SEARCHING, detail="Szukam serwera...")
        return await discover_server(DISCOVERY_TIMEOUT_SECONDS)

    async def _wait_before_retry(self, reason: str) -> None:
        """Odczekanie przerywalne przez „Połącz ponownie" z menu zasobnika."""
        self._set_status(LinkState.SEARCHING, detail=f"{reason} Ponawiam...")
        logger.info(f"{reason} Ponowna próba za {RECONNECT_DELAY_SECONDS:.0f}s.")
        assert self._reconnect_now is not None
        self._reconnect_now.clear()
        try:
            await asyncio.wait_for(self._reconnect_now.wait(), timeout=RECONNECT_DELAY_SECONDS)
            logger.info("Ponowne połączenie wymuszone z menu.")
        except TimeoutError:
            pass

    @staticmethod
    def _build_vad(silence_duration_ms: float, amplitude_threshold: int) -> SilenceVadDetector:
        return SilenceVadDetector(
            frame_duration_ms=FRAME_DURATION_MS,
            silence_duration_ms=silence_duration_ms,
            amplitude_threshold=amplitude_threshold,
        )

    def _set_status(self, state: LinkState, server_url: str | None = None, detail: str = "") -> None:
        self._status = AppStatus(
            state=state, sender_id=self.sender_id, server_url=server_url, detail=detail
        )
        if self._on_status_change is not None:
            try:
                self._on_status_change(self._status)
            except Exception as err:
                # Awaria warstwy prezentacji nie może zabić połączenia — ten sam
                # wzorzec co obserwator prób w `ai/llm/router.py` po stronie serwera.
                logger.error(f"Błąd obserwatora stanu: {err}")

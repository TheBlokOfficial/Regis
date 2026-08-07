"""
Pętla heartbeat Kontrolera.

Co 30 sekund sprawdza dostępność zarejestrowanych klientów (WebSocket timeout)
oraz czyści nieaktywne sesje konwersacji (po 60s bezczynności).
"""
import asyncio
import logging
import time

import controller.core.app_state as app_state
import controller.core.client_store as client_store
import controller.core.session_store as session_store
import controller.core.event_bus as event_bus
from controller.core.connection_manager import client_manager

# Czas bezczynności (w sekundach) po którym sesja jest automatycznie czyszczona
SESSION_IDLE_TIMEOUT = 60.0

# Czas (w sekundach) po którym klient bez odpowiedzi jest usuwany z rejestru
CLIENT_TIMEOUT = 60.0

# Interwał pętli heartbeat (w sekundach)
HEARTBEAT_INTERVAL = 30.0


async def _heartbeat_loop() -> None:
    """
    Główna pętla heartbeat działająca jako task asyncio w tle.

    Wykonuje dwie operacje co HEARTBEAT_INTERVAL sekund:
    1. Czyści sesje konwersacji bez aktywności przez SESSION_IDLE_TIMEOUT.
    2. Usuwa klientów którzy nie aktualizowali last_seen przez CLIENT_TIMEOUT.
    """
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        now = time.time()

        # 1. Automatyczne czyszczenie nieaktywnych sesji
        expired_sids = [
            sid for sid, t in list(session_store.session_last_interaction_times.items())
            if now - t > SESSION_IDLE_TIMEOUT
        ]
        for sid in expired_sids:
            logging.info(f"[Heartbeat] Sesja '{sid}' nieaktywna przez {SESSION_IDLE_TIMEOUT}s — czyszczę historię.")
            session_store.clear_session_history(sid)

        # 2. Sprawdzanie zdrowia klientów (WebSocket timeout)
        for c in list(client_store.client_registry.values()):
            cid = c.get("id")
            if not cid:
                continue
            last_seen = c.get("last_seen", now)
            if now - last_seen > CLIENT_TIMEOUT:
                logging.info(f"[Heartbeat] Klient '{cid}' przekroczył timeout — usuwam z rejestru.")
                client_store.client_registry.pop(cid, None)
                client_manager.disconnect(cid)
                await event_bus.publish({"type": "client_unregistered", "id": cid})

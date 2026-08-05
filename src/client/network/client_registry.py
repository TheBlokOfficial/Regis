import json
import logging
import asyncio

from client.config import (
    save_settings, _get_settings, _get_client_id
)
from client.process_manager import (
    control_service, ProcessAction, ProcessStatus,
    get_active_services_registration, get_all_services_status,
    DISPLAY_NAMES
)
from protocol.schemas import (
    ClientRegistrationRequest, ServiceName
)
from protocol.discovery import get_local_ip
from client.network.ws_transport import get_ws_client, get_ws_loop

logger = logging.getLogger(__name__)
_last_applied_config: dict | None = None


def apply_service_config(config_data: dict, from_registration: bool = False) -> None:
    """
    Aplikuje profil konfiguracji usług otrzymany z Kontrolera i synchronizuje stany podprocesów.
    Startuje nowe usługi, przeładowuje zmodyfikowane oraz zatrzymuje odznaczone usługi.
    """
    global _last_applied_config
    if _last_applied_config == config_data:
        return
    _last_applied_config = config_data

    # Zapisz tylko imię (jeśli uległo zmianie) – to element tożsamości
    if "name" in config_data:
        settings = _get_settings()
        if settings.get("instance_name") != config_data["name"]:
            settings["instance_name"] = config_data["name"]
            save_settings(settings)

    services = config_data.get("services", {})
    enabled_list = [DISPLAY_NAMES.get(s, s) for s in services.keys()]
    enabled_str = ", ".join(enabled_list) if enabled_list else "brak"

    if not from_registration:
        logger.info(f"[Klient] Zastosowano nową konfigurację z Kontrolera (Web UI). Aktywne usługi: {enabled_str}.")

    # Pętla synchronizacji podprocesów mikrousług z wykorzystaniem silnych typów
    active_statuses = get_all_services_status()
    target_services = [ServiceName.OLLAMA_WORKER.value, ServiceName.LLM.value, ServiceName.AUDIO.value, ServiceName.SATELLITE.value]

    for s_name in target_services:
        display_label = DISPLAY_NAMES.get(s_name, s_name.capitalize())
        if s_name in services:
            if active_statuses.get(s_name) == ProcessStatus.RUNNING:
                if not from_registration:
                    logger.info(f"[Klient] Przeładowuję usługę: {display_label}")
                    control_service(s_name, ProcessAction.RESTART, services[s_name])
            else:
                logger.info(f"[Klient] Uruchamiam usługę: {display_label}")
                control_service(s_name, ProcessAction.START, services[s_name])
        else:
            if active_statuses.get(s_name) == ProcessStatus.RUNNING:
                logger.info(f"[Klient] Wyłączam usługę: {display_label}")
                control_service(s_name, ProcessAction.STOP)
    
    if not from_registration:
        register()


# Alias wstecznej kompatybilności
apply_node_config = apply_service_config


def register() -> None:
    """Wysyła ramkę rejestracyjną Aplikacji Klienckiej przez podłączone gniazdo WebSocket."""
    ws_loop = get_ws_loop()
    ws_client = get_ws_client()
    
    if not ws_loop or not ws_client:
        logger.warning("Nie można wysłać rejestracji: brak aktywnego gniazda WebSocket.")
        return

    client_id = _get_client_id()
    reg_request = ClientRegistrationRequest(
        id=client_id,
        name=client_id,
        host=get_local_ip(),
        services=get_active_services_registration(),
    )
    
    payload = json.dumps({
        "type": "register",
        "data": reg_request.model_dump()
    })
    
    asyncio.run_coroutine_threadsafe(ws_client.send(payload), ws_loop)
    logger.info(f"Przesłano ramkę rejestracji Klienta '{client_id}' przez WebSocket.")


def unregister() -> None:
    """Wyrejestrowanie klienta po stronie serwera odbywa się automatycznie przy zamknięciu gniazda WS."""
    pass

from protocol.schemas import ServiceAction
from client.proc_utils import cleanup_orphaned_processes
from client.subservices import WorkerSubservice, SatelliteSubservice, BaseSubservice

# Globalny Rejestr Usług
SERVICES: dict[str, BaseSubservice] = {
    "worker": WorkerSubservice(),
    "satellite": SatelliteSubservice(),
}

def control_service(name: str, action: ServiceAction | str, config_data: dict = None) -> bool:
    """Zarządza stanem pojedynczej usługi (start, stop, restart)."""
    if name not in SERVICES:
        return False
        
    srv = SERVICES[name]
    act = action if isinstance(action, ServiceAction) else ServiceAction(action)

    match act:
        case ServiceAction.START:
            return srv.start(config_data)
        case ServiceAction.STOP:
            srv.stop()
            return True
        case ServiceAction.RESTART:
            srv.stop()
            return srv.start(config_data)
        case _:
            return False

def stop_all_services() -> None:
    for srv in SERVICES.values():
        srv.stop()

def get_all_services_status() -> dict:
    return {name: srv.get_status_payload() for name, srv in SERVICES.items()}
    
def get_active_services_registration() -> dict:
    reg = {}
    for name, srv in SERVICES.items():
        payload = srv.get_registration_payload()
        if payload:
            reg[name] = payload
    return reg

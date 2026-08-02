from client.proc_utils import cleanup_orphaned_processes
from client.subservices import WorkerSubservice, SatelliteSubservice, BaseSubservice

# Globalny Rejestr Usług
SERVICES: dict[str, BaseSubservice] = {
    "worker": WorkerSubservice(),
    "satellite": SatelliteSubservice(),
}

def control_service(name: str, action: str, config_data: dict = None) -> bool:
    """Zarządza stanem pojedynczej usługi. 
    Wspierane akcje: 'start', 'stop', 'restart'."""
    if name not in SERVICES:
        return False
        
    srv = SERVICES[name]
    
    # Rozpakowujemy jeśli podano Enum
    act = action.value if hasattr(action, "value") else action

    if act == "start":
        return srv.start(config_data)
    elif act == "stop":
        srv.stop()
        return True
    elif act == "restart":
        srv.stop()
        return srv.start(config_data)
        
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

import asyncio
import logging
from contextlib import asynccontextmanager

from core.logger import setup_logging
setup_logging("controller")

from fastapi import FastAPI

from core import config
from integrations.ha_client import HomeAssistantClient
from core.tools_registry import ToolsRegistry
import controller.registry as registry
from controller.registry import router_workers, router_satellites
from controller.tools import router_tools
from controller.router import router_chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uruchamia i zatrzymuje usługi Kontrolera."""
    settings = config.load_settings()
    registry._settings_cache.update(settings)
    aliases = config.load_aliases()
    virtual_groups = config.load_virtual_groups()
    rooms = config.load_rooms()

    registry.ha_client = HomeAssistantClient(
        url=settings.get("ha_url", "http://192.168.0.50:8123"),
        token=settings.get("ha_token", "TWÓJ_TOKEN_TUTAJ"),
        aliases=aliases,
        virtual_groups=virtual_groups
    )

    active_tier = settings.get("active_tier", "butler")
    registry.tools_registry = ToolsRegistry(registry.ha_client, active_tier, rooms=rooms)

    logging.info(f"Regis Controller uruchomiony. Tier: {active_tier}")
    heartbeat_task = asyncio.create_task(registry._heartbeat_loop())
    
    from core.discovery import start_discovery_server, get_local_ip
    controller_port = 8000 # Domyślny port kontrolera
    local_ip = get_local_ip()
    discovery_url = f"http://{local_ip}:{controller_port}"
    start_discovery_server(discovery_url)
    
    yield
    heartbeat_task.cancel()
    logging.info("Regis Controller zatrzymany.")


app = FastAPI(lifespan=lifespan)

app.include_router(router_workers)
app.include_router(router_satellites)
app.include_router(router_tools)
app.include_router(router_chat)

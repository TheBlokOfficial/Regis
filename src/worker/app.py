import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core import config
from worker.registration import registration_manager
from worker.routes import router
from worker.service import inference_service

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządza cyklem życia Węzła Roboczego."""
    settings = config.load_settings()
    active_tier = settings.get("active_tier", "butler")
    tier_defaults = {
        "butler": {"model": "qwen2.5:1.5b", "temperature": 0.1, "history_limit": 0},
        "regis":  {"model": "qwen3.5:9b",  "temperature": 0.1, "history_limit": 10},
    }
    tier_cfg = tier_defaults.get(active_tier, tier_defaults["butler"])
    selected_model = settings.get("selected_model", tier_cfg["model"])

    inference_service.initialize(
        model_name=selected_model,
        tier=active_tier,
        temperature=tier_cfg["temperature"],
        history_limit=tier_cfg.get("history_limit", settings.get("history_limit", 10))
    )

    registration_manager.register(settings, active_tier, selected_model)
    await registration_manager.start_heartbeat()

    yield

    registration_manager.unregister()
    inference_service.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(router)

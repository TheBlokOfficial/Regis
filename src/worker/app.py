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
    selected_model = settings.get("selected_model", "qwen3.5:9b")
    worker_priority = int(settings.get("worker_priority", 100))

    inference_service.initialize(
        model_name=selected_model,
        temperature=0.1,
        history_limit=settings.get("history_limit", 10)
    )

    registration_manager.register(settings, selected_model, worker_priority)
    await registration_manager.start_heartbeat()

    yield

    registration_manager.unregister()
    inference_service.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(router)

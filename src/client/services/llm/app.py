"""
Konfiguracja i inicjalizacja aplikacji FastAPI usługi LLM.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from client.services.llm.service import llm_service
from client.services.llm.registration import registration_manager
from client.services.llm.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządza uruchomieniem silnika VRAM oraz pętli rejestracji."""
    await llm_service.start_engine()
    await registration_manager.start_registration()
    yield
    registration_manager.stop_registration()
    await llm_service.stop_engine()


app = FastAPI(lifespan=lifespan)
app.include_router(router)

"""Eksportuje instancję aplikacji FastAPI dla zachowania kompatybilności wstecznej."""
from controller.embedded_worker.app import app

__all__ = ["app"]

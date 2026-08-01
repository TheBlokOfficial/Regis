"""Eksportuje instancję aplikacji FastAPI dla zachowania kompatybilności wstecznej."""
from worker.app import app

__all__ = ["app"]

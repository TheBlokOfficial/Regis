import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Union, Optional


def setup_logging(
    service_name: str = "regis",
    logs_dir: Optional[Union[str, Path]] = None
) -> None:
    """Konfiguruje zunifikowany system logowania dla dowolnej usługi w projekcie Regis.

    Ustawia handlery:
    - TimedRotatingFileHandler (DEBUG) — plik <logs_dir>/<service_name>.log z rotacją o północy.
    - StreamHandler (INFO) — konsola z czytelnym formatem czasu.

    Args:
        service_name: Nazwa usługi (np. "client", "controller", "satellite", "ollama_worker").
        logs_dir: Opcjonalna własna ścieżka do katalogu logów. Jeśli None, domyślnie katalog 'logs/'.
    """
    if logs_dir is None:
        logs_dir = os.path.join(os.getcwd(), "logs")

    os.makedirs(logs_dir, exist_ok=True)
    log_filename = os.path.join(logs_dir, f"{service_name}.log")

    file_fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    file_handler = TimedRotatingFileHandler(
        log_filename,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)

    root_logger = logging.getLogger()

    if root_logger.handlers:
        root_logger.handlers.clear()

    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Ujednolicenie logów Uvicorna — przekierowanie do głównego logera z timestampami
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        u_logger = logging.getLogger(logger_name)
        u_logger.handlers.clear()
        u_logger.propagate = True

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)

    logging.info(f"System logowania uruchomiony. Plik: {log_filename}")


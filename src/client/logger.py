import logging
from logging.handlers import TimedRotatingFileHandler
import os

from client.config import LOGS_DIR


def setup_logging(service_name: str = "regis") -> None:
    """Konfiguruje globalny system logowania dla danej usługi.

    Ustawia handlery:
    - TimedRotatingFileHandler (DEBUG) — plik logs/<service_name>.log z rotacją o północy.
    - StreamHandler (INFO) — konsola (przekierowanie logów na stdout).

    Args:
        service_name: Nazwa usługi, np. "client" lub "controller".
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_filename = os.path.join(LOGS_DIR, f"{service_name}.log")

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

    # Wyciszamy szum z bibliotek zewnętrznych — interesuje nas tylko nasz kod
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)

    logging.info(f"System logowania uruchomiony. Plik: {log_filename}")

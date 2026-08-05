import logging
import logging.handlers
import os
from datetime import date


def setup_logging(service_name: str = "regis") -> None:
    """Konfiguruje globalny system logowania dla danej usługi.

    Ustawia dwa handlery:
    - FileHandler (DEBUG) — plik logs/<service_name>_YYYY-MM-DD.log
    - StreamHandler (INFO)  — konsola (bez zaśmiecania debugami)

    Wywołaj raz przy starcie usługi, zanim cokolwiek innego zostanie zaimportowane.

    Args:
        service_name: Nazwa usługi, np. "node" lub "controller".
                      Staje się prefiksem nazwy pliku logu.
    """
    from pathlib import Path
    controller_dir = Path(__file__).resolve().parent
    log_dir = controller_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_filename = log_dir / f"{service_name}_{date.today().isoformat()}.log"

    file_fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)

    root_logger = logging.getLogger()

    # Zabezpieczenie przed podwójną konfiguracją przy restarcie (np. hot-reload Uvicorn)
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

from pathlib import Path
from common.logger import setup_logging as _common_setup_logging


def setup_logging(service_name: str = "regis") -> None:
    """Konfiguruje globalny system logowania dla Kontrolera.

    Deleguje konfigurację do zunifikowanego modułu common.logger.
    """
    controller_dir = Path(__file__).resolve().parent
    log_dir = controller_dir / "logs"
    _common_setup_logging(service_name=service_name, logs_dir=log_dir)


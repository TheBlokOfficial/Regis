from client.config import LOGS_DIR
from common.logger import setup_logging as _common_setup_logging


def setup_logging(service_name: str = "regis") -> None:
    """Konfiguruje globalny system logowania dla aplikacji klienckiej.

    Deleguje konfigurację do zunifikowanego modułu common.logger.
    """
    _common_setup_logging(service_name=service_name, logs_dir=LOGS_DIR)


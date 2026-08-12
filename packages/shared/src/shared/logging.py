import logging
import sys


class MinimalColorFormatter(logging.Formatter):
    """Minimalistyczny, czytelny formatter logów z kolorowaniem wybranych elementów."""

    RESET = "\x1b[0m"
    GRAY = "\x1b[90m"
    CYAN = "\x1b[36m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    RED = "\x1b[31m"
    BOLD_RED = "\x1b[31;1m"

    LEVEL_COLORS = {
        logging.DEBUG: CYAN,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    DATE_FORMAT = "%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        # 1. Czas w kolorze szarym (subtelny, nie odciąga uwagi)
        asctime = self.formatTime(record, self.DATE_FORMAT)
        time_str = f"{self.GRAY}[{asctime}]{self.RESET}"

        # 2. Poziom logu z kolorem (TYLKO tag [INFO   ], [ERROR  ] itp.)
        color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        level_str = f"{color}[{record.levelname:<7s}]{self.RESET}"


        # 3. Nazwa modułu w delikatnym cyjanie (upraszczamy 'uvicorn.error' do 'uvicorn')
        display_name = "uvicorn" if record.name == "uvicorn.error" else record.name
        name_str = f"{self.CYAN}[{display_name}]{self.RESET}"


        # 4. Treść wiadomości w domyślnym kolorze tekstu terminala
        message = record.getMessage()

        return f"{time_str} {level_str} {name_str} {message}"


def setup_logging(level: str = "INFO") -> None:
    """Inicjalizuje spójne, minimalistyczne logowanie dla całej aplikacji."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Czyszczenie starych handlerów
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(MinimalColorFormatter())
    root_logger.addHandler(stream_handler)

    # Przekierowanie logów Uvicorna do naszego root handlera
    for uvicorn_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(uvicorn_logger_name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Zwraca nazwaną instancję loggera."""
    return logging.getLogger(name)

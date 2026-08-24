import re
from pathlib import Path
from typing import Any, Callable, Generic, Type, TypeVar

from pydantic import BaseModel

from shared.logging import get_logger

logger = get_logger("regis.shared.config")

# Typ generyczny dla modeli konfiguracji dziedziczących po Pydantic BaseModel
T = TypeVar("T", bound=BaseModel)

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def sanitize_identifier(value: str, *, field_name: str = "id") -> str:
    """Waliduje identyfikator przeznaczony do budowy nazwy pliku na dysku (np. session_id, backend_id).

    Dopuszcza wyłącznie znaki alfanumeryczne, '_' oraz '-', by uniemożliwić directory
    traversal (np. '../../etc/passwd') lub inne nieprzewidziane znaki w nazwie pliku.

    :raises ValueError: jeśli identyfikator jest pusty, zbyt długi lub zawiera niedozwolone znaki.
    """
    if not _SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(
            f"Nieprawidłowy {field_name}: '{value}'. Dozwolone są wyłącznie znaki "
            f"alfanumeryczne, '_' oraz '-' (maks. 128 znaków)."
        )
    return value


class ConfigStore(Generic[T]):
    """Generyczny, silnie typowany menedżer przechowywania konfiguracji w plikach JSON.

    Zarządza wczytywaniem, walidacją oraz trwałym zapisem dowolnego modelu Pydantic.
    Każda usługa w monorepo wskazuje własną klasę modelu oraz dowolną ścieżkę do pliku.
    """

    def __init__(
        self,
        model_cls: Type[T],
        config_path: str | Path,
    ) -> None:
        """Inicjalizuje menedżer konfiguracji dla danego typu modelu i ścieżki pliku.

        :param model_cls: Klasa Pydantic reprezentująca schemat konfiguracji.
        :param config_path: Ścieżka do pliku JSON (wraz z katalogiem i nazwą pliku).
        """
        self.model_cls = model_cls
        self.config_path = Path(config_path).resolve()

    def load(self, default_factory: Callable[[], T] | None = None) -> T:
        """Wczytuje plik konfiguracji i waliduje dane w stosunku do modelu Pydantic.

        Jeśli plik nie istnieje, automatycznie tworzy katalog oraz plik z wartościami domyślnymi.

        :param default_factory: Opcjonalna funkcja tworząca domyślną instancję modelu.
        :return: Zwalidowany obiekt konfiguracji typu T.
        """
        if not self.config_path.exists():
            logger.info(
                f"Plik konfiguracji nie istnieje pod adresem [{self.config_path}]. "
                f"Tworzenie pliku z wartościami domyślnymi..."
            )
            default_config = default_factory() if default_factory else self.model_cls()
            self.save(default_config)
            return default_config

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                content = f.read()

            config_instance = self.model_cls.model_validate_json(content)
            logger.debug(f"Pomyślnie wczytano konfigurację z [{self.config_path}]")
            return config_instance
        except Exception as e:
            logger.error(f"Błąd podczas wczytywania pliku konfiguracji [{self.config_path}]: {e}")
            raise RuntimeError(f"Nie udało się wczytać konfiguracji z {self.config_path}: {e}") from e

    def save(self, config: T) -> None:
        """Zapisuje podany obiekt konfiguracji w formacie czytelnego pliku JSON na dysku.

        Automatycznie tworzy niezbędny katalog macierzysty, jeśli ten nie istnieje.

        :param config: Obiekt modelu Pydantic typu T do zapisania.
        """
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            json_data = config.model_dump_json(indent=2)

            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(json_data)

            logger.info(f"Pomyślnie zapisano konfigurację do [{self.config_path}]")
        except Exception as e:
            logger.error(f"Błąd podczas zapisu pliku konfiguracji [{self.config_path}]: {e}")
            raise RuntimeError(f"Nie udało się zapisać konfiguracji do {self.config_path}: {e}") from e

    def update(self, config: T, **kwargs: Any) -> T:
        """Aktualizuje wybrane pola w obiekcie konfiguracji i zapisuje go od razu na dysku.

        :param config: Aktualny obiekt konfiguracji.
        :param kwargs: Pola i nowe wartości do nadpisania.
        :return: Nowy, zaktualizowany obiekt konfiguracji.
        """
        updated_data = config.model_dump()
        updated_data.update(kwargs)
        updated_config = self.model_cls.model_validate(updated_data)
        self.save(updated_config)
        return updated_config


def get_service_root(start_path: Path | str, marker_filename: str = "pyproject.toml") -> Path:
    """Odnajduje główny katalog usługi w monorepo (szukając pliku marker_filename w górę drzewa).

    :param start_path: Ścieżka początkowa (zazwyczaj __file__ wywołującego modułu).
    :param marker_filename: Nazwa pliku wskaźnikowego (domyślnie 'pyproject.toml').
    :return: Bezwzględna ścieżka Path do głównego katalogu usługi.
    """
    current = Path(start_path).resolve()
    if current.is_file():
        current = current.parent

    for parent in [current, *current.parents]:
        if (parent / marker_filename).exists():
            return parent
    return current

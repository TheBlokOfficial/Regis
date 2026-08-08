"""
Generyczny loader odczytu i zapisu plików konfiguracyjnych w module config.
"""
import os
from pathlib import Path
from typing import Any, TypeVar, Type
from dotenv import load_dotenv
from pydantic import BaseModel

from controller.config.storage import JSONStorage

load_dotenv()

CONTROLLER_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("REGIS_DATA_DIR", CONTROLLER_DIR / "data"))
CONFIG_DIR = Path(os.getenv("REGIS_CONFIG_DIR", CONTROLLER_DIR / "config"))

T = TypeVar("T", bound=BaseModel)


def load_config(
    name: str,
    schema: Type[T] | None = None,
    default: dict[str, Any] | None = None,
) -> T | dict[str, Any]:
    """Ładuje dowolny plik konfiguracyjny JSON z folderu data/ po nazwie.
    
    Opcjonalnie dokonuje konwersji i walidacji w oparciu o schemat Pydantic.

    Args:
        name (str): Nazwa pliku konfiguracyjnego bez rozszerzenia (np. "settings", "network").
        schema (Type[T], optional): Schemat Pydantic do zmapowania słownika na silnie typowany obiekt.
        default (dict[str, Any], optional): Domyślny słownik w przypadku braku pliku.

    Returns:
        T | dict[str, Any]: Instancja schematu Pydantic lub czysty słownik.
    """
    file_path = DATA_DIR / f"{name}.json"
    if not file_path.exists() and (CONFIG_DIR / f"{name}.json").exists():
        file_path = CONFIG_DIR / f"{name}.json"

    raw_data = JSONStorage.read_json(file_path, default=default or {})

    if schema is not None:
        return schema.model_validate(raw_data)

    return raw_data


def save_config(name: str, data: dict[str, Any] | BaseModel) -> None:
    """Zapisuje słownik lub obiekt Pydantic pod wskazaną nazwą pliku JSON w folderze data/.
    
    Args:
        name (str): Nazwa pliku konfiguracyjnego bez rozszerzenia (np. "settings", "network").
        data (dict[str, Any] | BaseModel): Dane do zapisania.
    """
    file_path = DATA_DIR / f"{name}.json"
    if isinstance(data, BaseModel):
        payload = data.model_dump()
    else:
        payload = data
        
    JSONStorage.write_json(file_path, payload)


def _get_file_name_from_schema(schema_or_instance: Any) -> str:
    """Pomocnicza funkcja do bezpiecznego odczytu Meta.file_name z klasy lub instancji."""
    meta = getattr(schema_or_instance, "Meta", None)
    file_name = getattr(meta, "file_name", None) if meta else None
    if not file_name or not isinstance(file_name, str):
        raise AttributeError(
            f"Klasa lub instancja '{getattr(schema_or_instance, '__name__', type(schema_or_instance).__name__)}' "
            "nie posiada zdefiniowanej klasy 'Meta' z polem 'file_name'."
        )
    return file_name


def load(schema_class: Type[T]) -> T:
    """Ładuje konfigurację bezpośrednio na podstawie klasy schematu Pydantic."""
    file_name = _get_file_name_from_schema(schema_class)
    return load_config(file_name, schema=schema_class)


def save(instance: BaseModel) -> None:
    """Zapisuje instancję schematu Pydantic na podstawie jej metadanych w `Meta.file_name`."""
    file_name = _get_file_name_from_schema(instance)
    save_config(file_name, instance)


def get_controller_url() -> str:
    """Zwraca wyznaczony adres URL serwera Kontrolera."""
    from controller.core.state import _settings_cache
    controller_url = _settings_cache.get("controller_url", "auto")
    if controller_url == "auto" or "127.0.0.1" in controller_url or "localhost" in controller_url:
        from protocol.discovery import get_local_ip
        controller_url = f"http://{get_local_ip()}:8000"
    return controller_url

